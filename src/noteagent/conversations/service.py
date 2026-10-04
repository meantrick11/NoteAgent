"""Conversation metadata, active-branch tracking, and checkpoint reads/writes.

The application owns the *active* head: the head checkpoint id lives in
``conversation_branches``, never in the saver's notion of the latest checkpoint.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping
from collections.abc import Callable

from sqlalchemy import select, update, delete
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, sessionmaker

from noteagent.conversations.checkpoints import (
    CHECKPOINT_NS,
    CheckpointRuntime,
    checkpoint_id_of,
    next_versions,
    state_to_checkpoint,
    thread_config,
)
from noteagent.conversations.models import ConversationBranch, ConversationRun, UserMessageBoundary
from noteagent.conversations.contracts import (
    ConversationNotFound, TurnAlreadyClaimed, ConversationBusy,
    StaleConversation, StateView, PreparedTurn,
)
from noteagent.conversations.leases import expires_at, reconcile_expired_runs, refresh_lease
from noteagent.conversations.records import (
    ConversationRecord,
    GraphState,
    MessageRecord,
    initial_state,
    message_dict_from_record,
    record_from_ui,
    validate_state,
)
from noteagent.db.models import Conversation
from noteagent.recovery.models import RecoveryJob, WorkspaceState

logger = logging.getLogger(__name__)


class ConversationService:
    """Reads and writes conversation state; owns where the active head points."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        runtime: CheckpointRuntime,
        workspace_seq_provider=None,
    ) -> None:
        self._session_factory = session_factory
        self._runtime = runtime
        self._workspace_seq = workspace_seq_provider or (lambda: 0)

    # ---- metadata ---------------------------------------------------------

    def get(self, conversation_id: str) -> ConversationRecord | None:
        """Return the sidebar record, or None when missing or malformed."""
        with self._session_factory() as session:
            conversation = self._load(session, conversation_id, required=False)
            return _to_conversation(conversation) if conversation is not None else None

    async def create_conversation(self, title: str) -> ConversationRecord:
        """Create metadata and its root branch, then write the first safe checkpoint."""
        with self._session_factory() as session:
            conversation = Conversation(title=title, state_backend="checkpoint")
            session.add(conversation)
            session.flush()
            branch = ConversationBranch(
                conversation_id=conversation.id, checkpoint_ns=CHECKPOINT_NS
            )
            session.add(branch)
            session.flush()
            conversation.active_branch_id = branch.id
            session.commit()
            conversation_id = str(conversation.id)
            branch_id = str(branch.id)

        config = await self.write_state(
            conversation_id,
            initial_state(branch_id=branch_id),
            branch_id=branch_id,
            publish=True,
        )
        logger.info(
            "created conversation=%s branch=%s head=%s",
            conversation_id,
            branch_id,
            checkpoint_id_of(config),
        )
        record = self.get(conversation_id)
        assert record is not None  # just committed above
        return record

    def active_branch_id(self, conversation_id: str) -> str:
        """The branch new turns are appended to."""
        with self._session_factory() as session:
            conversation = self._load(session, conversation_id)
            if conversation.active_branch_id is None:
                raise ConversationNotFound(conversation_id)
            return str(conversation.active_branch_id)

    def active_head_config(self, conversation_id: str) -> dict[str, Any]:
        """Explicit config for the active branch's head checkpoint."""
        with self._session_factory() as session:
            conversation = self._load(session, conversation_id)
            branch = self._branch(session, conversation)
            if branch.head_checkpoint_id is None:
                raise ConversationNotFound(conversation_id)
            return thread_config(str(conversation.id), branch.head_checkpoint_id)

    # ---- state ------------------------------------------------------------

    async def get_state(
        self, conversation_id: str, config: Mapping[str, Any] | None = None
    ) -> StateView:
        """Read a state version; defaults to the application's active head."""
        resolved = dict(config) if config is not None else self.active_head_config(
            conversation_id
        )
        return await self.read_state(resolved)

    async def read_state(self, config: Mapping[str, Any]) -> StateView:
        """Read one explicit checkpoint config, validating its schema version."""
        tuple_ = await self._runtime.saver.aget_tuple(dict(config))
        if tuple_ is None:
            raise ConversationNotFound(checkpoint_id_of(config) or "unknown checkpoint")
        values = validate_state(tuple_.checkpoint["channel_values"])
        return StateView(values=values, config=dict(config))

    async def write_state(
        self,
        conversation_id: str,
        values: Mapping[str, Any],
        *,
        branch_id: str | None = None,
        parent_checkpoint_id: str | None = None,
        publish: bool = False,
    ) -> dict[str, Any]:
        """Persist a new state version.

        With ``publish=False`` the checkpoint exists but the application head does not
        move, which is how a candidate fork stays invisible until it is committed.
        """
        checkpoint = state_to_checkpoint(
            values, next_versions(self._runtime.saver, values)
        )
        if publish:
            with self._session_factory() as session:
                conversation = self._load(session, conversation_id)
                branch = self._branch(session, conversation)
                expected_head = branch.head_checkpoint_id
                expected_generation = conversation.generation
        metadata = {
            "source": "update",
            "step": int(values.get("generation", 0) or 0),
            "parents": {CHECKPOINT_NS: parent_checkpoint_id} if parent_checkpoint_id else {},
        }
        saved = await self._runtime.saver.aput(
            thread_config(conversation_id),
            checkpoint,
            metadata,
            checkpoint["channel_versions"],
        )
        new_id = checkpoint_id_of(saved)
        if publish:
            if branch_id is None:
                raise ValueError("publish requires a branch_id")
            self.publish_head(
                conversation_id, branch_id, new_id or "",
                expected_checkpoint_id=expected_head,
                expected_generation=expected_generation,
            )
        return saved

    def publish_head(
        self, conversation_id: str, branch_id: str, checkpoint_id: str, *,
        expected_checkpoint_id: str | None, expected_generation: int,
        expected_revision: int | None = None, require_no_active_run: bool = False,
    ) -> None:
        """Point one branch's head at a checkpoint and make it the active branch.

        Single application-DB transaction; the checkpoint was written to the saver
        beforehand, which is the compensating protocol, not one atomic transaction.
        """
        with self._session_factory() as session:
            self._publish(session, conversation_id, branch_id, checkpoint_id,
                          expected_checkpoint_id, expected_generation,
                          expected_revision, require_no_active_run)
            session.commit()
            logger.info(
                "published conversation=%s branch=%s head=%s",
                conversation_id,
                branch_id,
                checkpoint_id,
            )

    def _publish(self, session, conversation_id, branch_id, checkpoint_id,
                 expected_checkpoint_id, expected_generation,
                 expected_revision=None, require_no_active_run=False):
        """CAS both rows in the caller's transaction; rollback on either mismatch.

        ``require_no_active_run`` makes draft mutations refuse to move the head while a
        prepared/running/interrupted turn owns the conversation. ``expected_revision``
        additionally rejects a publisher whose read head is already stale.
        """
        parsed = uuid.UUID(conversation_id)
        self._lock_conversation(session, conversation_id)
        if require_no_active_run and self._has_active_run(session, parsed):
            raise ConversationBusy(conversation_id)
        conditions = [
            Conversation.id == parsed,
            Conversation.active_branch_id == uuid.UUID(branch_id),
            Conversation.generation == expected_generation,
        ]
        if expected_revision is not None:
            conditions.append(Conversation.revision == expected_revision)
        moved = session.execute(update(Conversation).where(*conditions).values(
            updated_at=datetime.now(timezone.utc),
            revision=Conversation.revision + 1,
        ))
        if moved.rowcount != 1:
            raise StaleConversation(conversation_id)
        moved = session.execute(update(ConversationBranch).where(
            ConversationBranch.id == uuid.UUID(branch_id),
            ConversationBranch.conversation_id == parsed,
            ConversationBranch.head_checkpoint_id == expected_checkpoint_id,
        ).values(head_checkpoint_id=checkpoint_id))
        if moved.rowcount != 1:
            raise StaleConversation(conversation_id)

    def _has_active_run(self, session: Session, conversation_id: uuid.UUID) -> bool:
        """True when a turn still owns the conversation (caller's transaction)."""
        return session.scalar(select(ConversationRun.id).where(
            ConversationRun.conversation_id == conversation_id,
            ConversationRun.status.in_(("prepared", "running", "interrupted")),
        )) is not None

    def _lock_conversation(self, session: Session, conversation_id: str) -> Conversation:
        """Serialize publishers and claimers without blocking the async event loop."""
        try:
            row = session.scalar(select(Conversation).where(
                Conversation.id == uuid.UUID(conversation_id)
            ).with_for_update(nowait=True).execution_options(populate_existing=True))
        except OperationalError as exc:
            if getattr(exc.orig, "sqlstate", None) == "55P03":
                raise ConversationBusy(conversation_id) from None
            raise
        if row is None:
            raise ConversationNotFound(conversation_id)
        return row

    async def review_pending_draft(
        self, conversation_id: str, apply: Callable[[dict], dict],
        *, expected_revision: int | None = None, allow_absent: bool = False,
    ) -> dict:
        """Hold the conversation row through validation, side effects and publication.

        Persist the invisible cleared candidate before calling the note writer. All
        claimers and publishers use this same nonblocking row lock. Full durable file
        compensation on a database failure remains the notes-mutation phase's job.
        """
        with self._session_factory() as session:
            conversation = self._lock_conversation(session, conversation_id)
            if self._has_active_run(session, conversation.id):
                raise ConversationBusy(conversation_id)
            revision = int(conversation.revision or 0)
            if expected_revision is not None and expected_revision != revision:
                raise StaleConversation(conversation_id)
            branch = self._branch(session, conversation)
            head = branch.head_checkpoint_id
            view = await self.read_state(thread_config(conversation_id, head))
            draft = view.values.get("pending_draft")
            if not draft:
                if allow_absent:
                    return {**apply({}), "state_revision": revision}
                return {"error": "no pending draft"}
            values = {**view.values, "pending_draft": None}
            saved = await self.write_state(
                conversation_id, values, branch_id=str(branch.id),
                parent_checkpoint_id=head, publish=False,
            )
            result = apply({**draft, "_state_revision": revision, "_branch_id": str(branch.id), "_head_id": head})
            if "error" in result:
                return result
            if result.get("_mutation_operation"):
                values["notes_commit"] = result["notes_commit"]
                values["workspace_seq"] = result["workspace_seq"]
                saved = await self.write_state(conversation_id, values, branch_id=str(branch.id), parent_checkpoint_id=head, publish=False)
            self._publish(
                session, conversation_id, str(branch.id), checkpoint_id_of(saved),
                head, conversation.generation, revision, True,
            )
            if result.get("_mutation_operation"):
                from noteagent.recovery.models import MutationRecord
                session.execute(update(MutationRecord).where(MutationRecord.operation_id == result["_mutation_operation"]).values(status="published"))
                session.execute(update(WorkspaceState).where(WorkspaceState.maintenance_job_id == result["_mutation_operation"]).values(maintenance_job_id=None, maintenance_kind=None))
            session.commit()
            return {k: v for k, v in {**result, "state_revision": revision + 1}.items() if not k.startswith("_")}

    # ---- recovery: fork, publish ------------------------------------------

    async def fork_for_edit(
        self,
        conversation_id: str,
        before_checkpoint_id: str,
        candidate_values: Mapping[str, Any],
        request_id: str,
        operation_id: str,
    ) -> PreparedTurn:
        """Prepare a new branch forked from a boundary and accept one edited message.

        Idempotent by ``request_id``: a repeat returns the already-prepared turn. The
        candidate checkpoint is written unpublished; nothing becomes active until
        :meth:`publish_recovery`.
        """
        self.reconcile_expired_runs()
        turn_id = uuid.uuid4()
        user_message_id = uuid.UUID(candidate_values["ui_messages"][-1]["id"])
        lease_token = str(uuid.uuid4())
        with self._session_factory() as session:
            conversation = self._load(session, conversation_id)
            session.execute(select(Conversation.id).where(
                Conversation.id == conversation.id).with_for_update())
            session.refresh(conversation)
            existing = session.scalar(select(ConversationRun).where(
                ConversationRun.request_id == request_id))
            if existing is not None:
                boundary = session.scalar(select(UserMessageBoundary).where(UserMessageBoundary.message_id == existing.user_message_id))
                if boundary is None:
                    raise StaleConversation(conversation_id)
                config = thread_config(conversation_id, existing.accepted_checkpoint_id)
                return PreparedTurn(conversation_id=conversation_id, branch_id=str(existing.branch_id),
                    turn_id=str(existing.turn_id), user_message_id=str(existing.user_message_id),
                    generation=existing.generation, run_id=str(existing.id), request_id=request_id,
                    before_config=thread_config(conversation_id, boundary.before_checkpoint_id),
                    config=config, head_config=config, lease_token=existing.lease_token)
            if self._has_active_run(session, conversation.id):
                raise ConversationBusy(conversation_id)
            old_branch = self._branch(session, conversation)
            branch = ConversationBranch(
                conversation_id=conversation.id,
                parent_branch_id=old_branch.id,
                fork_checkpoint_id=before_checkpoint_id,
                checkpoint_ns=CHECKPOINT_NS,
            )
            session.add(branch)
            session.flush()
            branch_id = str(branch.id)
            generation = int(conversation.generation or 0) + 1
            old_branch_id = str(old_branch.id)
            session.commit()

        values = dict(candidate_values)
        values.update(
            branch_id=branch_id,
            generation=generation,
            current_turn_id=str(turn_id),
            current_user_id=str(user_message_id),
            run_status="running",
            tool_rounds=0,
            runtime_messages=[],
            citation_registry=[],
            tool_steps=[],
            announced_tool_ids=[],
        )
        # Save a before-message boundary on the new branch with the restored workspace.
        baseline = dict(values)
        baseline["ui_messages"] = list(values["ui_messages"][:-1])
        baseline["working_records"] = list(values["working_records"][:-1])
        baseline["run_status"] = "idle"
        before_saved = await self.write_state(conversation_id, baseline, branch_id=branch_id,
            parent_checkpoint_id=before_checkpoint_id, publish=False)
        before_checkpoint_id = checkpoint_id_of(before_saved)
        values["ui_messages"][-1] = {**values["ui_messages"][-1], "turn_id": str(turn_id)}
        values["working_records"][-1] = dict(values["ui_messages"][-1])
        saved = await self.write_state(
            conversation_id, values, branch_id=branch_id,
            parent_checkpoint_id=before_checkpoint_id, publish=False,
        )
        with self._session_factory() as session:
            run = ConversationRun(
                conversation_id=uuid.UUID(conversation_id),
                branch_id=uuid.UUID(branch_id),
                turn_id=turn_id,
                user_message_id=user_message_id,
                generation=generation,
                checkpoint_id=checkpoint_id_of(saved),
                accepted_checkpoint_id=checkpoint_id_of(saved),
                status="prepared",
                request_id=request_id,
                lease_token=lease_token,
                lease_expires_at=expires_at(),
            )
            session.add(run)
            session.add(UserMessageBoundary(conversation_id=uuid.UUID(conversation_id),
                branch_id=uuid.UUID(branch_id), message_id=user_message_id, turn_id=turn_id,
                before_checkpoint_ns=CHECKPOINT_NS, before_checkpoint_id=before_checkpoint_id,
                workspace_seq=int(candidate_values.get("workspace_seq") or 0), recoverable=True))
            session.commit()
            run_id = str(run.id)
        logger.info(
            "recovery fork conversation=%s branch=%s run=%s op=%s",
            conversation_id, branch_id, run_id, operation_id,
        )
        return PreparedTurn(
            conversation_id=conversation_id,
            branch_id=branch_id,
            turn_id=str(turn_id),
            user_message_id=str(user_message_id),
            generation=generation,
            run_id=run_id,
            request_id=request_id,
            before_config=thread_config(conversation_id, before_checkpoint_id),
            config=saved,
            head_config=saved,
            lease_token=lease_token,
        )

    def recovery_context(self, conversation_id: str) -> tuple[str, int, int] | None:
        """(active_branch_id, generation, revision) for a recovery CAS, or None."""
        with self._session_factory() as session:
            conversation = self._load(session, conversation_id, required=False)
            if conversation is None or conversation.active_branch_id is None:
                return None
            return (
                str(conversation.active_branch_id),
                int(conversation.generation or 0),
                int(conversation.revision or 0),
            )

    def publish_recovery(
        self,
        *,
        conversation_id: str,
        old_branch_id: str,
        new_branch_id: str,
        candidate_checkpoint_id: str,
        job_id: str,
        prepared_turn_id: str,
        expected_generation: int,
        expected_revision: int,
    ) -> None:
        """CAS-switch to the recovered branch and release maintenance in one transaction.

        The candidate checkpoint already exists but was invisible; this is the single
        atomic switch that makes the new branch active, marks the job succeeded and
        clears the durable maintenance flag.
        """
        cid = uuid.UUID(conversation_id)
        with self._session_factory() as session:
            moved = session.execute(update(Conversation).where(
                Conversation.id == cid,
                Conversation.active_branch_id == uuid.UUID(old_branch_id),
                Conversation.generation == expected_generation,
                Conversation.revision == expected_revision,
            ).values(
                active_branch_id=uuid.UUID(new_branch_id),
                generation=expected_generation + 1,
                revision=Conversation.revision + 1,
                updated_at=datetime.now(timezone.utc),
            ))
            if moved.rowcount != 1:
                raise StaleConversation(conversation_id)
            moved = session.execute(update(ConversationBranch).where(
                ConversationBranch.id == uuid.UUID(new_branch_id),
                ConversationBranch.conversation_id == cid,
            ).values(head_checkpoint_id=candidate_checkpoint_id))
            if moved.rowcount != 1:
                raise StaleConversation(conversation_id)
            session.execute(update(WorkspaceState).where(WorkspaceState.id == 1).values(
                maintenance_job_id=None, maintenance_kind=None,
            ))
            job = session.get(RecoveryJob, uuid.UUID(job_id)) if job_id else None
            if job is not None:
                job.status = "succeeded"
                job.stage = "succeeded"
                job.prepared_turn_id = prepared_turn_id
            session.commit()
            logger.info(
                "recovery published conversation=%s branch=%s job=%s",
                conversation_id, new_branch_id, job_id,
            )

    def recoverable_message_ids(self, conversation_id):
        with self._session_factory() as session:
            conversation = self._load(session, conversation_id)
            rows = session.scalars(select(UserMessageBoundary).where(
                UserMessageBoundary.conversation_id == conversation.id,
                UserMessageBoundary.recoverable.is_(True)))
            return {str(row.message_id) for row in rows}

    async def list_messages(self, conversation_id: str) -> list[MessageRecord] | None:
        """Project the active checkpoint's display history; None when unknown."""
        try:
            view = await self.get_state(conversation_id)
        except ConversationNotFound:
            return None
        return [record_from_ui(item) for item in view.values.get("ui_messages", [])]

    # ---- pending draft (checkpoint-backed) --------------------------------

    async def get_pending_draft(self, conversation_id: str) -> dict | None:
        """The active head's pending draft, or None when there is none."""
        try:
            view = await self.get_state(conversation_id)
        except ConversationNotFound:
            return None
        return view.values.get("pending_draft")

    async def update_pending_draft(
        self, conversation_id: str, content: str, *, expected_revision: int | None = None
    ) -> dict | None:
        """Rewrite only the pending draft body, publishing a new head via CAS.

        Returns None when there is no draft. The publish is pinned to the head this
        method read, and refused outright while a turn owns the conversation, so a
        draft edit can neither clobber a newer head nor race a running turn.
        """
        view = await self.get_state(conversation_id)
        draft = view.values.get("pending_draft")
        if not draft:
            return None
        revision = self._require_expected_revision(conversation_id, expected_revision)
        updated = dict(draft)
        updated["content"] = content
        await self._republish_state(
            conversation_id, view, {"pending_draft": updated}, revision
        )
        return updated

    async def clear_pending_draft(
        self, conversation_id: str, *, expected_revision: int | None = None
    ) -> bool:
        """Drop the pending draft, publishing a new head via CAS. False when absent."""
        view = await self.get_state(conversation_id)
        if not view.values.get("pending_draft"):
            return False
        revision = self._require_expected_revision(conversation_id, expected_revision)
        await self._republish_state(
            conversation_id, view, {"pending_draft": None}, revision
        )
        return True

    def _require_expected_revision(
        self, conversation_id: str, expected: int | None
    ) -> int:
        """Return the current head revision; refuse when the caller's token is stale."""
        current = self.current_revision(conversation_id)
        if expected is not None and expected != current:
            raise StaleConversation(conversation_id)
        return current

    def current_revision(self, conversation_id: str) -> int:
        """The conversation row's revision, or 0 when the id is unknown."""
        try:
            parsed = uuid.UUID(conversation_id)
        except ValueError:
            raise ConversationNotFound(conversation_id) from None
        with self._session_factory() as session:
            conversation = session.get(Conversation, parsed)
            if conversation is None:
                raise ConversationNotFound(conversation_id)
            return int(conversation.revision or 0)

    async def _republish_state(
        self, conversation_id: str, view: StateView, changes: Mapping[str, Any],
        expected_revision: int,
    ) -> dict[str, Any]:
        """Publish one new state version pinned to the head this view was read from.

        The candidate is written first, then CAS'd against ``view``'s exact checkpoint
        id, generation and revision: a head that moved since the read is rejected
        instead of being silently refreshed and overwritten.
        """
        values = dict(view.values)
        values.update(changes)
        branch_id = str(values.get("branch_id") or self.active_branch_id(conversation_id))
        saved = await self.write_state(
            conversation_id,
            values,
            branch_id=branch_id,
            parent_checkpoint_id=checkpoint_id_of(view.config),
            publish=False,
        )
        self.publish_head(
            conversation_id,
            branch_id,
            checkpoint_id_of(saved) or "",
            expected_checkpoint_id=checkpoint_id_of(view.config),
            expected_generation=int(values.get("generation", 0) or 0),
            expected_revision=expected_revision,
            require_no_active_run=True,
        )
        return saved

    # ---- active run (explicit resume) -------------------------------------

    def get_active_run(self, conversation_id: str) -> dict[str, Any] | None:
        """The conversation's prepared/running/interrupted run, if any.

        Exposed on the detail endpoint so a client that lost its stream can resume the
        exact run instead of re-sending the question (which would be rejected).
        """
        self.reconcile_expired_runs()
        try:
            parsed = uuid.UUID(conversation_id)
        except ValueError:
            return None
        with self._session_factory() as session:
            run = session.scalar(select(ConversationRun).where(
                ConversationRun.conversation_id == parsed,
                ConversationRun.status.in_(("prepared", "running", "interrupted")),
            ))
            if run is None:
                return None
            return {
                "run_id": str(run.id),
                "status": run.status,
                "turn_id": str(run.turn_id) if run.turn_id else None,
                "user_message_id": str(run.user_message_id) if run.user_message_id else None,
                "request_id": run.request_id,
                "generation": run.generation,
                "checkpoint_id": run.checkpoint_id,
            }

    # ---- turns ------------------------------------------------------------

    async def prepare_turn(
        self, conversation_id: str, question: str, request_id: str,
        *, expected_revision: int | None = None,
    ) -> PreparedTurn:
        """Claim the run and write the user message before any model call.

        The boundary records the head as it was *before* this message, which is the
        safe point a later edit of this message must fork from.
        """
        turn_id = uuid.uuid4()
        user_message_id = uuid.uuid4()
        lease_token = str(uuid.uuid4())
        self.reconcile_expired_runs()
        with self._session_factory() as session:
            conversation = self._lock_conversation(session, conversation_id)
            if expected_revision is not None and int(conversation.revision or 0) != expected_revision:
                raise StaleConversation(conversation_id)
            branch = self._branch(session, conversation)
            before_checkpoint_id = branch.head_checkpoint_id
            if before_checkpoint_id is None:
                raise ConversationNotFound(conversation_id)
            claimed = session.scalar(
                select(ConversationRun).where(ConversationRun.request_id == request_id)
            )
            if claimed is not None:
                raise TurnAlreadyClaimed(request_id)
            if session.scalar(select(ConversationRun.id).where(
                ConversationRun.conversation_id == conversation.id,
                ConversationRun.status.in_(("prepared", "running", "interrupted")),
            )) is not None:
                raise ConversationBusy(conversation_id)
            run = ConversationRun(
                conversation_id=conversation.id,
                branch_id=branch.id,
                turn_id=turn_id,
                user_message_id=user_message_id,
                generation=int(conversation.generation or 0),
                checkpoint_id=before_checkpoint_id,
                status="prepared",
                request_id=request_id,
                lease_token=lease_token,
                lease_expires_at=expires_at(),
            )
            session.add(run)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                if session.scalar(select(ConversationRun.id).where(
                    ConversationRun.request_id == request_id,
                )) is not None:
                    raise TurnAlreadyClaimed(request_id) from None
                raise ConversationBusy(conversation_id) from None
            branch_id = str(branch.id)
            generation = int(conversation.generation or 0)
            run_id = str(run.id)

        try:
            return await self._accept_turn(
                conversation_id, question, branch_id, generation, run_id,
                turn_id, user_message_id, before_checkpoint_id,
                lease_token, request_id,
            )
        except BaseException:
            # An unpublished candidate is harmless history. Only remove a claim
            # that never atomically accepted its user and boundary; cancellation
            # must release it too. Published/running claims are never removed.
            with self._session_factory() as session:
                session.execute(delete(ConversationRun).where(
                    ConversationRun.id == uuid.UUID(run_id),
                    ConversationRun.status == "prepared",
                    ConversationRun.lease_token == lease_token,
                ))
                session.commit()
            raise

    async def _accept_turn(self, conversation_id, question, branch_id, generation,
                           run_id, turn_id, user_message_id, before_checkpoint_id,
                           lease_token, request_id):
        before_config = thread_config(conversation_id, before_checkpoint_id)
        values = dict((await self.read_state(before_config)).values)
        user_record = MessageRecord(
            id=str(user_message_id),
            conversation_id=conversation_id,
            role="user",
            content=question,
            created_at=datetime.now(timezone.utc),
            turn_id=str(turn_id),
            tool_name=None,
            tool_arguments=None,
            output_preview=None,
            truncated=False,
            status=None,
        )
        entry = message_dict_from_record(user_record)
        values.update(
            ui_messages=list(values.get("ui_messages") or []) + [entry],
            working_records=list(values.get("working_records") or []) + [entry],
            current_turn_id=str(turn_id),
            current_user_id=str(user_message_id),
            current_question=question,
            tool_rounds=0,
            runtime_messages=[],
            citation_registry=[],
            tool_steps=[],
            announced_tool_ids=[],
            branch_id=branch_id,
            generation=generation,
            run_status="running",
        )
        saved = await self.write_state(
            conversation_id,
            values,
            branch_id=branch_id,
            parent_checkpoint_id=before_checkpoint_id,
            publish=False,
        )
        # Read the workspace seq *before* opening the publish transaction: the provider
        # takes its own session, and a nested session on the same connection would roll
        # back the publish we are about to commit.
        workspace_seq = int(self._workspace_seq() or 0)
        with self._session_factory() as session:
            self._publish(session, conversation_id, branch_id,
                          checkpoint_id_of(saved), before_checkpoint_id, generation)
            run = session.get(ConversationRun, uuid.UUID(run_id))
            if run is None or run.status != "prepared" or run.lease_token != lease_token:
                raise StaleConversation(conversation_id)
            run.status = "running"
            run.checkpoint_id = checkpoint_id_of(saved)
            run.accepted_checkpoint_id = checkpoint_id_of(saved)
            run.lease_expires_at = expires_at()
            session.add(
                UserMessageBoundary(
                    conversation_id=uuid.UUID(conversation_id),
                    branch_id=uuid.UUID(branch_id),
                    message_id=user_message_id,
                    turn_id=turn_id,
                    before_checkpoint_ns=CHECKPOINT_NS,
                    before_checkpoint_id=before_checkpoint_id,
                    workspace_seq=workspace_seq,
                    recoverable=True,
                    reason=None,
                )
            )
            session.commit()
        logger.info(
            "prepared turn conversation=%s turn=%s run=%s",
            conversation_id,
            turn_id,
            run_id,
        )
        return PreparedTurn(
            conversation_id=conversation_id,
            branch_id=branch_id,
            turn_id=str(turn_id),
            user_message_id=str(user_message_id),
            generation=generation,
            run_id=run_id,
            request_id=request_id,
            before_config=before_config,
            config=saved,
            head_config=saved,
            lease_token=lease_token,
        )

    def resume_turn(
        self, run_id: str, *, conversation_id: str | None = None,
        expected_revision: int | None = None,
    ) -> PreparedTurn:
        """Explicitly claim an interrupted run; never automatically call the model."""
        self.reconcile_expired_runs()
        with self._session_factory() as session:
            try:
                parsed_run = uuid.UUID(run_id)
            except ValueError:
                raise ConversationNotFound(run_id) from None
            run = session.get(ConversationRun, parsed_run)
            if run is None or (conversation_id is not None and str(run.conversation_id) != conversation_id):
                raise ConversationNotFound(run_id)
            conversation = self._lock_conversation(session, str(run.conversation_id))
            if expected_revision is not None and conversation.revision != expected_revision:
                raise StaleConversation(str(run.conversation_id))
            run = session.scalar(select(ConversationRun).where(
                ConversationRun.id == parsed_run).with_for_update().execution_options(populate_existing=True))
            if run is None:
                raise ConversationNotFound(run_id)
            branch = self._branch(session, conversation)
            if run.branch_id != branch.id or run.generation != conversation.generation:
                raise StaleConversation(str(run.conversation_id))
            if run.accepted_checkpoint_id != branch.head_checkpoint_id:
                raise StaleConversation(str(run.conversation_id))
            if run.status != "interrupted":
                raise TurnAlreadyClaimed(run.request_id)
            boundary = session.scalar(select(UserMessageBoundary).where(
                UserMessageBoundary.conversation_id == run.conversation_id,
                UserMessageBoundary.message_id == run.user_message_id,
                UserMessageBoundary.branch_id == run.branch_id,
            ))
            if boundary is None or run.checkpoint_id is None:
                raise StaleConversation(str(run.conversation_id))
            lease_token = str(uuid.uuid4())
            changed = session.execute(update(ConversationRun).where(
                ConversationRun.id == run.id, ConversationRun.status == "interrupted",
            ).values(status="running", lease_token=lease_token, lease_expires_at=expires_at()))
            if changed.rowcount != 1:
                raise TurnAlreadyClaimed(run.request_id)
            prepared = PreparedTurn(
                conversation_id=str(run.conversation_id), branch_id=str(run.branch_id),
                turn_id=str(run.turn_id), user_message_id=str(run.user_message_id),
                generation=run.generation, run_id=run_id, request_id=run.request_id,
                before_config=thread_config(str(run.conversation_id), boundary.before_checkpoint_id),
                config=thread_config(str(run.conversation_id), run.checkpoint_id),
                head_config=thread_config(str(run.conversation_id), branch.head_checkpoint_id),
                lease_token=lease_token,
            )
            session.commit()
            return prepared

    def claim_prepared(self, run_id: str, *, conversation_id: str | None = None,
                       expected_revision: int | None = None) -> PreparedTurn:
        """Claim an accepted but not-yet-started prepared run (recovery fork).

        Used after a recovery publishes its branch: the forked turn already holds the
        edited user message, so claiming it must never re-accept the message.
        """
        self.reconcile_expired_runs()
        with self._session_factory() as session:
            run = session.scalar(select(ConversationRun).where(
                ConversationRun.id == uuid.UUID(run_id)).with_for_update())
            if run is None:
                raise ConversationNotFound(run_id)
            if conversation_id and str(run.conversation_id) != conversation_id:
                raise ConversationNotFound(run_id)
            conversation = self._load(session, str(run.conversation_id))
            if expected_revision is not None and conversation.revision != expected_revision:
                raise StaleConversation(str(run.conversation_id))
            branch = self._branch(session, conversation)
            if run.branch_id != branch.id:
                raise StaleConversation(str(run.conversation_id))
            if run.accepted_checkpoint_id != branch.head_checkpoint_id:
                raise StaleConversation(str(run.conversation_id))
            if run.status != "prepared":
                raise TurnAlreadyClaimed(run.request_id)
            lease_token = str(uuid.uuid4())
            changed = session.execute(update(ConversationRun).where(
                ConversationRun.id == run.id, ConversationRun.status == "prepared",
            ).values(status="running", lease_token=lease_token, lease_expires_at=expires_at()))
            if changed.rowcount != 1:
                raise TurnAlreadyClaimed(run.request_id)
            config = thread_config(str(run.conversation_id), run.accepted_checkpoint_id)
            prepared = PreparedTurn(
                conversation_id=str(run.conversation_id), branch_id=str(run.branch_id),
                turn_id=str(run.turn_id), user_message_id=str(run.user_message_id),
                generation=run.generation, run_id=run_id, request_id=run.request_id,
                before_config=config, config=config,
                head_config=thread_config(str(run.conversation_id), branch.head_checkpoint_id),
                lease_token=lease_token,
            )
            session.commit()
            return prepared

    def finish_run(self, prepared: PreparedTurn, checkpoint_id: str, status: str):
        """Commit terminal state and active head together, or publish neither."""
        if status not in ("completed", "failed"):
            raise ValueError("graph did not reach a terminal state")
        with self._session_factory() as session:
            self._publish(session, prepared.conversation_id, prepared.branch_id,
                          checkpoint_id, checkpoint_id_of(prepared.head_config),
                          prepared.generation)
            changed = session.execute(update(ConversationRun).where(
                ConversationRun.id == uuid.UUID(prepared.run_id),
                ConversationRun.status == "running",
                ConversationRun.lease_token == prepared.lease_token,
            ).values(status=status, checkpoint_id=checkpoint_id,
                     lease_token=None, lease_expires_at=None))
            if changed.rowcount != 1:
                raise StaleConversation(prepared.conversation_id)
            session.commit()

    async def record_run_checkpoint(self, prepared: PreparedTurn, config: Mapping[str, Any]):
        """Record only a durable snapshot from this run while it still owns the head."""
        values = (await self.read_state(config)).values
        if (values.get("branch_id") != prepared.branch_id
                or values.get("generation") != prepared.generation
                or values.get("current_turn_id") != prepared.turn_id):
            raise StaleConversation(prepared.conversation_id)
        with self._session_factory() as session:
            conversation = self._load(session, prepared.conversation_id)
            branch = self._branch(session, conversation)
            if (str(branch.id) != prepared.branch_id
                    or conversation.generation != prepared.generation
                    or branch.head_checkpoint_id != checkpoint_id_of(prepared.head_config)):
                raise StaleConversation(prepared.conversation_id)
            changed = session.execute(update(ConversationRun).where(
                ConversationRun.id == uuid.UUID(prepared.run_id),
                ConversationRun.status == "running",
                ConversationRun.lease_token == prepared.lease_token,
            ).values(checkpoint_id=checkpoint_id_of(config)))
            if changed.rowcount != 1:
                raise StaleConversation(prepared.conversation_id)
            session.commit()

    def reconcile_expired_runs(self):
        reconcile_expired_runs(self._session_factory)

    def refresh_run_lease(self, prepared: PreparedTurn):
        if not refresh_lease(self._session_factory, prepared.run_id, prepared.lease_token):
            raise StaleConversation(prepared.conversation_id)

    def interrupt_run(self, prepared: PreparedTurn):
        """An old executor must never mutate a newer resume attempt's claim."""
        with self._session_factory() as session:
            session.execute(update(ConversationRun).where(
                ConversationRun.id == uuid.UUID(prepared.run_id),
                ConversationRun.status == "running",
                ConversationRun.lease_token == prepared.lease_token,
            ).values(status="interrupted", lease_token=None, lease_expires_at=None))
            session.commit()

    # ---- internals --------------------------------------------------------

    def _load(
        self, session: Session, conversation_id: str, *, required: bool = True
    ) -> Conversation | None:
        """Fetch a conversation row, rejecting malformed ids like the legacy store."""
        try:
            parsed = uuid.UUID(conversation_id)
        except ValueError:
            raise ConversationNotFound(conversation_id) from None
        conversation = session.get(Conversation, parsed)
        if conversation is None and required:
            raise ConversationNotFound(conversation_id)
        return conversation

    def _branch(self, session: Session, conversation: Conversation) -> ConversationBranch:
        """The conversation's active branch row."""
        if conversation.active_branch_id is None:
            raise ConversationNotFound(str(conversation.id))
        branch = session.get(ConversationBranch, conversation.active_branch_id)
        if branch is None:
            raise ConversationNotFound(str(conversation.id))
        return branch


def _to_conversation(row: Conversation) -> ConversationRecord:
    """Map an ORM Conversation to its plain DTO."""
    return ConversationRecord(
        id=str(row.id),
        title=row.title,
        created_at=row.created_at,
        updated_at=row.updated_at,
        running_summary=row.running_summary,
        summary_watermark_turn_id=(
            str(row.summary_watermark_turn_id)
            if row.summary_watermark_turn_id is not None
            else None
        ),
        pending_draft=dict(row.pending_draft) if row.pending_draft else None,
        state_backend=row.state_backend,
        generation=int(row.generation or 0),
        revision=int(row.revision or 0),
    )
