"""Import legacy (message-table) conversations into the checkpoint backend.

Import is a compensating protocol, not one transaction: a candidate checkpoint is
written to the saver, verified against the legacy rows, then the application row
CAS-switches ``state_backend`` and points its new branch head at the candidate.
A failure before the switch leaves the legacy tables authoritative and the
conversation retryable; the candidate checkpoint is harmless unpublished history.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from noteagent.chat.history import ConversationStore
from noteagent.conversations.checkpoints import CHECKPOINT_NS, checkpoint_id_of
from noteagent.conversations.contracts import StaleConversation
from noteagent.conversations.models import ConversationBranch
from noteagent.conversations.records import (
    MessageRecord,
    initial_state,
    message_dict_from_record,
)
from noteagent.conversations.service import ConversationService
from noteagent.db.models import Conversation, Message

logger = logging.getLogger(__name__)

# Old histories predate the shadow Git, so no safe boundary can be reconstructed.
HISTORY_NOT_RECOVERABLE = "history_not_recoverable"

_KNOWN_ROLES = {"user", "assistant", "tool"}


@dataclass(slots=True)
class ConversationPlan:
    """What a single legacy conversation contributes to an import."""

    conversation_id: str
    title: str
    messages: int
    users: int
    assistants: int
    tools: int
    has_summary: bool
    has_pending_draft: bool
    errors: list[str] = field(default_factory=list)

    @property
    def importable(self) -> bool:
        return not self.errors


@dataclass(slots=True)
class MigrationReport:
    """Aggregate counts and per-conversation problems for one scan or import run."""

    scanned: int = 0
    importable: int = 0
    imported: int = 0
    already_imported: int = 0
    skipped: int = 0
    failed: int = 0
    messages: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)
    plans: list[ConversationPlan] = field(default_factory=list)


class ConversationMigrator:
    """Reads legacy conversations and republishes them as checkpoint state."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        service: ConversationService,
        *,
        legacy: ConversationStore | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._service = service
        self._legacy = legacy or ConversationStore(session_factory)

    # ---- read-only planning ----------------------------------------------

    def dry_run(self, *, conversation_id: str | None = None) -> MigrationReport:
        """Count what would move, without writing anything.

        Already-migrated conversations are counted as ``already_imported`` and are
        never revisited; only legacy rows are planned.
        """
        report = MigrationReport()
        with self._session_factory() as session:
            stmt = select(Conversation)
            if conversation_id:
                stmt = stmt.where(Conversation.id == uuid.UUID(conversation_id))
            for row in session.scalars(stmt.order_by(Conversation.created_at)):
                report.scanned += 1
                if row.state_backend == "checkpoint":
                    report.already_imported += 1
                    continue
                plan = self._plan_one(session, row)
                report.plans.append(plan)
                report.messages += plan.messages
                if not plan.importable:
                    report.skipped += 1
                    report.errors.extend((plan.conversation_id, e) for e in plan.errors)
                else:
                    report.importable += 1
        return report

    # ---- import -----------------------------------------------------------

    async def import_all(
        self, *, conversation_id: str | None = None, batch_id: str | None = None
    ) -> MigrationReport:
        """Import every importable legacy conversation, one at a time.

        A failure on one conversation is recorded and the run continues; the
        conversation stays legacy and can be retried with the same batch id.
        """
        batch = batch_id or uuid.uuid4().hex
        report = self.dry_run(conversation_id=conversation_id)
        for plan in report.plans:
            if not plan.importable:
                continue
            try:
                moved = await self.import_conversation(plan.conversation_id, batch)
            except Exception as exc:  # one bad history must not abort the batch
                logger.warning(
                    "import failed conversation=%s error=%s",
                    plan.conversation_id, type(exc).__name__,
                )
                report.failed += 1
                report.errors.append((plan.conversation_id, str(exc)))
            else:
                if moved:
                    report.imported += 1
                else:
                    report.already_imported += 1
        return report

    async def import_conversation(self, conversation_id: str, batch_id: str) -> bool:
        """Import one conversation; returns False when it was already migrated."""
        with self._session_factory() as session:
            row = session.get(Conversation, uuid.UUID(conversation_id))
            if row is None:
                raise KeyError(conversation_id)
            if row.state_backend == "checkpoint":
                return False
            legacy_ui = self._legacy.list_messages(conversation_id) or []
            working = self._legacy.list_persistent_after_watermark(conversation_id)
            summary = row.running_summary
            watermark = (
                str(row.summary_watermark_turn_id)
                if row.summary_watermark_turn_id is not None
                else None
            )
            pending_draft = dict(row.pending_draft) if row.pending_draft else None

        branch_id = str(uuid.uuid4())
        values = self._build_state(
            branch_id, legacy_ui, working, summary, watermark, pending_draft
        )
        saved = await self._service.write_state(
            conversation_id, values, branch_id=branch_id, publish=False
        )
        candidate_id = checkpoint_id_of(saved)
        await self._verify(saved, legacy_ui)
        self._switch_backend(conversation_id, branch_id, candidate_id, batch_id)
        logger.info(
            "imported conversation=%s messages=%d",
            conversation_id, len(legacy_ui),
        )
        return True

    # ---- internals --------------------------------------------------------

    def _plan_one(self, session: Session, row: Conversation) -> ConversationPlan:
        roles = list(session.scalars(
            select(Message.role).where(Message.conversation_id == row.id)
        ))
        plan = ConversationPlan(
            conversation_id=str(row.id),
            title=row.title,
            messages=len(roles),
            users=roles.count("user"),
            assistants=roles.count("assistant"),
            tools=roles.count("tool"),
            has_summary=bool(row.running_summary),
            has_pending_draft=row.pending_draft is not None,
        )
        unknown = sorted({r for r in roles if r not in _KNOWN_ROLES})
        if unknown:
            plan.errors.append(f"unrecognized message roles: {', '.join(unknown)}")
        if row.pending_draft is not None and not isinstance(row.pending_draft, dict):
            plan.errors.append("pending_draft is not an object")
        return plan

    def _build_state(
        self,
        branch_id: str,
        legacy_ui: list[MessageRecord],
        working: list[MessageRecord],
        summary: str | None,
        watermark: str | None,
        pending_draft: dict | None,
    ) -> dict:
        """Compose the candidate checkpoint from the legacy projection."""
        state = dict(initial_state(branch_id=branch_id))
        ui_entries: list[dict] = []
        for record in legacy_ui:
            entry = message_dict_from_record(record)
            if record.role == "user":
                entry["edit_unavailable_reason"] = HISTORY_NOT_RECOVERABLE
            ui_entries.append(entry)
        state.update(
            ui_messages=ui_entries,
            working_records=[message_dict_from_record(r) for r in working],
            running_summary=summary,
            summary_watermark_turn_id=watermark,
            pending_draft=pending_draft,
            notes_commit=None,
            workspace_seq=0,
            run_status="idle",
        )
        return state

    async def _verify(self, saved: dict, legacy_ui: list[MessageRecord]) -> None:
        """Compare the read-back candidate against the legacy rows before publishing."""
        view = await self._service.read_state(saved)
        ui = view.values.get("ui_messages") or []
        if [m.get("id") for m in ui] != [r.id for r in legacy_ui]:
            raise RuntimeError("imported message ids do not match the legacy rows")
        if [m.get("content") for m in ui] != [r.content for r in legacy_ui]:
            raise RuntimeError("imported message content does not match the legacy rows")

    def _switch_backend(
        self, conversation_id: str, branch_id: str, checkpoint_id: str, batch_id: str
    ) -> None:
        """Publish the candidate: CAS the app row and point the new branch head at it."""
        cid = uuid.UUID(conversation_id)
        branch_uuid = uuid.UUID(branch_id)
        with self._session_factory() as session:
            changed = session.execute(update(Conversation).where(
                Conversation.id == cid,
                Conversation.state_backend != "checkpoint",
                Conversation.active_branch_id.is_(None),
            ).values(
                state_backend="checkpoint",
                active_branch_id=branch_uuid,
                migration_batch_id=batch_id,
            ))
            if changed.rowcount != 1:
                session.rollback()
                raise StaleConversation(conversation_id)
            session.add(ConversationBranch(
                id=branch_uuid,
                conversation_id=cid,
                parent_branch_id=None,
                fork_checkpoint_id=None,
                head_checkpoint_id=checkpoint_id,
                checkpoint_ns=CHECKPOINT_NS,
            ))
            session.commit()
