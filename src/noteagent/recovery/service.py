"""The recovery coordinator: a durable, idempotent restore state machine.

Stages (persisted after each one): ``prepared → restoring_files → reindexing →
preparing_state → publishing → succeeded``. The whole prepare runs under the exclusive
workspace gate; a failure keeps the durable maintenance flag set so read/chat/write stay
refused, and a retry continues the *same* plan instead of recomputing the rollback set.
The candidate checkpoint is written but stays invisible until :meth:`publish_recovery`
CAS-switches the active branch/head/generation and releases maintenance in one DB
transaction.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from noteagent.conversations.records import MessageRecord, message_dict_from_record
from noteagent.conversations.service import ConversationService
from noteagent.notes.mutations import NoteMutationService, Origin
from noteagent.recovery.gate import WorkspaceGate
from noteagent.recovery.models import MutationRecord, RecoveryJob, RecoveryPreview
from noteagent.recovery.planner import MutationView, RestorePlan, plan as build_plan
from noteagent.retrieval.repairs import IndexRepairService

logger = logging.getLogger(__name__)

STAGES = ("prepared", "restoring_files", "reindexing", "preparing_state", "publishing", "succeeded")
PREVIEW_TTL = timedelta(minutes=15)


class RecoveryError(RuntimeError):
    status = 400
    code = "recovery_error"
    retryable = False

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class RecoveryNotFound(RecoveryError):
    status = 404
    code = "recovery_not_found"


class PreviewExpired(RecoveryError):
    status = 409
    code = "preview_expired"
    retryable = True


class PlanConflict(RecoveryError):
    status = 409
    code = "conflict"


class ConfirmationRequired(RecoveryError):
    status = 409
    code = "confirmation_required"


class RecoveryJobView(dict):
    """Job payload returned to the HTTP layer."""


class RecoveryCoordinator:
    """Owns preview, start and retry for the whole-workspace rollback."""

    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        gate: WorkspaceGate,
        conversations: ConversationService,
        mutations: NoteMutationService,
        repairs: IndexRepairService,
        notes,
        retrieval_provider=None,
        faults=None,
    ) -> None:
        self._session_factory = session_factory
        self._gate = gate
        self._conversations = conversations
        self._mutations = mutations
        self._repairs = repairs
        self._notes = notes
        self._retrieval_provider = retrieval_provider or (lambda: None)
        self._faults = faults

    # ---- preview ----------------------------------------------------------

    async def preview(self, conversation_id: str, message_id: str, edited_content: str,
                      expected_revision: int | None = None) -> tuple[str, RestorePlan]:
        """Build and persist a pure preview; changes no body, index or head."""
        context = self._conversations.recovery_context(conversation_id)
        if context is None:
            raise RecoveryNotFound(conversation_id)
        stale_branch, generation, revision = context
        if expected_revision is not None and expected_revision != revision:
            raise PreviewExpired("conversation revision changed")

        boundary = self._boundary(conversation_id, message_id)
        if boundary is None:
            raise PlanConflict("history_not_recoverable")

        owned, later = self._split_mutations(conversation_id, boundary.get("workspace_seq") or 0)
        manifest = self._manifest()
        result = build_plan(
            conversation_id=conversation_id,
            branch_id=stale_branch,
            state_revision=revision,
            workspace_seq=self._gate.state().seq,
            boundary=boundary,
            owned_mutations=owned,
            later_mutations=later,
            current_manifest=manifest,
            affected_messages=[message_id],
            expires_at=(datetime.now(timezone.utc) + PREVIEW_TTL).isoformat(),
        )
        preview_id = str(uuid.uuid4())
        with self._session_factory() as session:
            session.add(RecoveryPreview(
                id=uuid.UUID(preview_id),
                conversation_id=uuid.UUID(conversation_id),
                message_id=uuid.UUID(message_id),
                expected_revision=revision,
                plan=result.as_dict(),
                expires_at=datetime.now(timezone.utc) + PREVIEW_TTL,
            ))
            session.commit()
        return preview_id, result

    # ---- start / retry ----------------------------------------------------

    async def start(self, preview_id: str, edited_content: str,
                    confirmed_files: list[str], operation_id: str) -> dict:
        """Validate the preview and run the restore machine (idempotent by operation_id)."""
        existing = self._job_by_operation(operation_id)
        if existing is not None:
            return existing

        with self._session_factory() as session:
            preview_row = session.get(RecoveryPreview, uuid.UUID(preview_id))
            if preview_row is None:
                raise RecoveryNotFound(preview_id)
            plan_dict = dict(preview_row.plan)
            expires = preview_row.expires_at
            conversation_id = str(preview_row.conversation_id)
            message_id = str(preview_row.message_id)
            expected_revision = preview_row.expected_revision

        if expires is not None and expires.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
            raise PreviewExpired("preview expired")
        if isinstance(plan_dict.get("conflicts"), list) and plan_dict["conflicts"]:
            raise PlanConflict("plan has conflicts")
        required = [
            change["path"] for change in plan_dict.get("file_changes", [])
            if change.get("action") in ("restore", "delete")
        ] + [change["path"] for change in plan_dict.get("folder_changes", [])]
        if required and not set(required).issubset(set(confirmed_files)):
            raise ConfirmationRequired("not all file changes were confirmed")

        context = self._conversations.recovery_context(conversation_id)
        if context is None:
            raise RecoveryNotFound(conversation_id)
        old_branch_id, generation, revision = context
        if revision != expected_revision:
            raise PreviewExpired("conversation changed since the preview")

        job_id = str(uuid.uuid4())
        with self._session_factory() as session:
            session.add(RecoveryJob(
                id=uuid.UUID(job_id),
                operation_id=operation_id,
                conversation_id=uuid.UUID(conversation_id),
                message_id=uuid.UUID(message_id),
                preview_id=uuid.UUID(preview_id),
                status="prepared",
                stage="prepared",
                plan=plan_dict,
                candidate_config={},
                edited_content=edited_content,
                confirmed_paths=list(confirmed_files),
            ))
            session.commit()
        self._gate.set_maintenance(job_id, "recovery")

        try:
            return await self._run(
                job_id=job_id, operation_id=operation_id, plan_dict=plan_dict,
                conversation_id=conversation_id, message_id=message_id,
                edited_content=edited_content, old_branch_id=old_branch_id,
                generation=generation, revision=revision,
            )
        except Exception as exc:  # noqa: BLE001 - failure keeps maintenance + failed row
            logger.exception("recovery job failed job=%s", job_id)
            self._update_job(job_id, status="failed", retryable=True, error=_public(exc))
            raise

    async def retry(self, job_id: str, operation_id: str) -> dict:
        """Continue the same persisted plan; never recompute the rollback set."""
        job = self._job_row(job_id)
        if job is None:
            raise RecoveryNotFound(job_id)
        if job["status"] == "succeeded":
            return job
        context = self._conversations.recovery_context(job["conversation_id"])
        if context is None:
            raise RecoveryNotFound(job["conversation_id"])
        old_branch_id, generation, revision = context
        try:
            return await self._run(
                job_id=job_id, operation_id=job.get("operation_id") or operation_id,
                plan_dict=job["plan"], conversation_id=job["conversation_id"],
                message_id=job["message_id"], edited_content=job.get("edited_content") or "",
                old_branch_id=old_branch_id, generation=generation, revision=revision,
            )
        except Exception as exc:  # noqa: BLE001
            self._update_job(job_id, status="failed", retryable=True, error=_public(exc))
            raise

    def get(self, job_id: str) -> dict:
        job = self._job_row(job_id)
        if job is None:
            raise RecoveryNotFound(job_id)
        return job

    # ---- the machine ------------------------------------------------------

    async def _run(self, *, job_id, operation_id, plan_dict, conversation_id, message_id,
                   edited_content, old_branch_id, generation, revision) -> dict:
        retrieval = self._retrieval_provider()

        with self._gate.operation("recovery", owner=job_id):
            boundary_row = self._boundary_row(message_id) or {}
            owned, _later = self._split_mutations(
                conversation_id, boundary_row.get("workspace_seq") or 0
            )
            self._stage(job_id, "restoring_files")
            restored = self._restore_files(plan_dict, operation_id, owned)
            self._fault("file_applied")

            self._stage(job_id, "reindexing")
            paths = restored["changed_paths"]
            if retrieval is not None and paths:
                self._repairs.repair_many(paths, retrieval, operation_id=f"{operation_id}:index")
            self._fault("index_rebuilt")

            self._stage(job_id, "preparing_state")
            prepared = await self._prepare_state(
                conversation_id, message_id, edited_content, operation_id, restored
            )
            self._fault("candidate_saved")
            self._fault("before_publish")

            self._stage(job_id, "publishing")
            self._conversations.publish_recovery(
                conversation_id=conversation_id,
                old_branch_id=old_branch_id,
                new_branch_id=prepared["branch_id"],
                candidate_checkpoint_id=prepared["checkpoint_id"],
                job_id=job_id,
                prepared_turn_id=prepared["run_id"],
                expected_generation=generation,
                expected_revision=revision,
            )
            self._fault("after_publish")
            self._update_job(
                job_id, status="succeeded", stage="succeeded",
                prepared_turn_id=prepared["run_id"], candidate_config=prepared["config"],
            )
        return self._job_row(job_id)

    def _restore_files(self, plan_dict: dict, operation_id: str,
                       owned: list[MutationView]) -> dict:
        restores: dict[str, bytes] = {}
        deletes: list[str] = []
        folders_create: list[str] = []
        folders_delete: list[str] = []
        for change in plan_dict.get("file_changes", []):
            path = change["path"]
            data = self._before_bytes(path, owned)
            if change.get("action") == "delete" or data is None:
                deletes.append(path)
            else:
                restores[path] = data
        for change in plan_dict.get("folder_changes", []):
            (folders_create if change.get("action") == "create" else folders_delete).append(
                change["path"].rstrip("/")
            )
        if not restores and not deletes and not folders_create and not folders_delete:
            # State-only recovery: no note version is created.
            return {"changed_paths": [], "commit": self._gate.state().current_commit}
        result = self._mutations.restore(
            restores=restores, deletes=deletes,
            folders_create=folders_create, folders_delete=folders_delete,
            origin=Origin(kind="recovery"), operation_id=f"{operation_id}:files",
            lock=False,  # the coordinator already holds the exclusive workspace gate
        )
        self._fault("git_committed")
        return {"changed_paths": result.paths, "commit": result.commit}

    def _before_bytes(self, path: str, owned: list[MutationView]) -> bytes | None:
        """The path's bytes before the earliest owned operation that touched it.

        Read straight from that operation's ``before_commit`` in the shadow store, which
        is the recoverable before-bytes recorded when the change was made.
        """
        store = self._mutations._versions  # noqa: SLF001 - same shadow store
        for mutation in sorted(owned, key=lambda m: m.workspace_seq):
            if path in mutation.paths and mutation.before_commit:
                return store.read_blob(mutation.before_commit, path)
        return None

    async def _prepare_state(self, conversation_id, message_id, edited_content,
                             operation_id, restored) -> dict:
        """Fork from the boundary, carry the edited user message, prepare the turn."""
        boundary = self._boundary_row(message_id)
        if boundary is None:
            raise PlanConflict("history_not_recoverable")
        before_checkpoint_id = boundary["before_checkpoint_id"]
        base = self._conversations.get_state(conversation_id, _config(conversation_id, before_checkpoint_id))
        values = dict((await base).values)
        values["ui_messages"] = list(values.get("ui_messages") or [])
        values["ui_messages"].append(message_dict_from_record(MessageRecord(
            id=str(uuid.uuid4()), conversation_id=conversation_id, role="user",
            content=edited_content, created_at=datetime.now(timezone.utc),
            turn_id=None, tool_name=None, tool_arguments=None, output_preview=None,
            truncated=False, status=None,
        )))
        values["working_records"] = list(values["ui_messages"])
        values["current_question"] = edited_content
        values["pending_draft"] = None
        values["notes_commit"] = restored.get("commit")
        values["workspace_seq"] = self._gate.state().seq
        prepared = await self._conversations.fork_for_edit(
            conversation_id, before_checkpoint_id, values,
            request_id=f"recovery-{operation_id}",
            operation_id=operation_id,
        )
        return {
            "branch_id": prepared.branch_id,
            "checkpoint_id": _checkpoint_id(prepared.config),
            "run_id": prepared.run_id,
            "config": {"branch_id": prepared.branch_id, "run_id": prepared.run_id},
        }

    # ---- ledger helpers ---------------------------------------------------

    def _boundary(self, conversation_id: str, message_id: str) -> dict | None:
        from noteagent.conversations.models import UserMessageBoundary
        with self._session_factory() as session:
            row = session.scalar(select(UserMessageBoundary).where(
                UserMessageBoundary.conversation_id == uuid.UUID(conversation_id),
                UserMessageBoundary.message_id == uuid.UUID(message_id),
            ))
            if row is None or not row.recoverable:
                return None
            return {
                "recoverable": True,
                "before_checkpoint_id": row.before_checkpoint_id,
                "workspace_seq": row.workspace_seq,
                "files": {},
            }

    def _boundary_row(self, message_id: str) -> dict | None:
        from noteagent.conversations.models import UserMessageBoundary
        with self._session_factory() as session:
            row = session.scalar(select(UserMessageBoundary).where(
                UserMessageBoundary.message_id == uuid.UUID(message_id)))
            if row is None:
                return None
            return {
                "before_checkpoint_id": row.before_checkpoint_id,
                "workspace_seq": row.workspace_seq,
                "before_commit": None,
            }

    def _split_mutations(self, conversation_id: str,
                         boundary_seq: int) -> tuple[list[MutationView], list[MutationView]]:
        """Owned = this conversation's mutations after the boundary; later = everyone else's."""
        cid = uuid.UUID(conversation_id)
        owned: list[MutationView] = []
        later: list[MutationView] = []
        with self._session_factory() as session:
            rows = session.scalars(select(MutationRecord).order_by(MutationRecord.workspace_seq))
            for row in rows:
                if int(row.workspace_seq or 0) <= boundary_seq:
                    continue  # before the boundary: neither undone nor a conflict
                view = MutationView(
                    operation_id=row.operation_id, origin_kind=row.origin_kind, kind=row.kind,
                    paths=list(row.paths or []), before_hashes=dict(row.before_hashes or {}),
                    before_commit=row.before_commit, after_commit=row.after_commit,
                    workspace_seq=row.workspace_seq, conversation_id=str(row.conversation_id or ""),
                )
                if row.origin_kind == "conversation" and row.conversation_id == cid:
                    owned.append(view)
                else:
                    later.append(view)
        return owned, later

    def _manifest(self) -> dict[str, str | None]:
        out: dict[str, str | None] = {}
        for name in self._notes.list_notes():
            try:
                out[name] = hashlib.sha256(self._notes.path_of(name).read_bytes()).hexdigest()
            except (OSError, ValueError):
                out[name] = None
        return out

    def _versions_ref(self):
        return self._mutations._versions  # noqa: SLF001 - coordinator owns the same store

    # ---- job persistence --------------------------------------------------

    def _stage(self, job_id: str, stage: str) -> None:
        self._update_job(job_id, stage=stage)
        logger.info("recovery job=%s stage=%s", job_id, stage)

    def _update_job(self, job_id: str, **fields) -> None:
        with self._session_factory() as session:
            row = session.get(RecoveryJob, uuid.UUID(job_id))
            if row is None:
                return
            for key, value in fields.items():
                setattr(row, key, value)
            session.commit()

    def _job_row(self, job_id: str) -> dict | None:
        with self._session_factory() as session:
            row = session.get(RecoveryJob, uuid.UUID(job_id))
            return _job_dict(row) if row is not None else None

    def _job_by_operation(self, operation_id: str) -> dict | None:
        with self._session_factory() as session:
            row = session.scalar(select(RecoveryJob).where(RecoveryJob.operation_id == operation_id))
            return _job_dict(row) if row is not None else None

    def _fault(self, stage: str) -> None:
        if self._faults is not None:
            self._faults.check(stage)


def _config(conversation_id: str, checkpoint_id: str) -> dict:
    from noteagent.conversations.checkpoints import thread_config
    return thread_config(conversation_id, checkpoint_id)


def _checkpoint_id(config: dict) -> str:
    from noteagent.conversations.checkpoints import checkpoint_id_of
    return checkpoint_id_of(config) or ""


def _public(exc: Exception) -> str:
    if isinstance(exc, RecoveryError):
        return exc.message
    return f"{type(exc).__name__}: {str(exc)[:200]}"


def _job_dict(row: RecoveryJob) -> dict:
    return {
        "job_id": str(row.id),
        "operation_id": row.operation_id,
        "conversation_id": str(row.conversation_id),
        "message_id": str(row.message_id),
        "status": row.status,
        "stage": row.stage,
        "plan": dict(row.plan or {}),
        "edited_content": row.edited_content,
        "prepared_turn_id": row.prepared_turn_id,
        "candidate_config": dict(row.candidate_config or {}),
        "error": row.error,
        "retryable": row.retryable,
    }
