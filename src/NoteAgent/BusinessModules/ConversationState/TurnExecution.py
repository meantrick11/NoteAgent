"""Conversation metadata, active-branch tracking, and checkpoint reads/writes.

The application owns the *active* head: the head checkpoint id lives in
``conversation_branches``, never in the saver's notion of the latest checkpoint.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping

from sqlalchemy import select, update, delete
from sqlalchemy.exc import IntegrityError

from NoteAgent.BusinessModules.ConversationState.ConversationCheckpoints import CHECKPOINT_NS, checkpoint_id_of, thread_config
from NoteAgent.BusinessModules.ConversationState.ConversationModels import ConversationRun, UserMessageBoundary
from NoteAgent.BusinessModules.ConversationState.ConversationContracts import ConversationNotFound, TurnAlreadyClaimed, ConversationBusy, StaleConversation, PreparedTurn
from NoteAgent.BusinessModules.ConversationState.TurnLeases import expires_at, reconcile_expired_runs, refresh_lease
from NoteAgent.BusinessModules.ConversationState.ConversationRecords import MessageRecord, message_dict_from_record

logger = logging.getLogger(__name__)


class ConversationRuns:
    """Internal execution-claim implementation used by ConversationService.

    The facade supplies state publication and row-locking helpers so acceptance
    remains in the same transactions as before the source reorganization.
    """

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
