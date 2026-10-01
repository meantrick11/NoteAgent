"""Conversation metadata, active-branch tracking, and checkpoint reads/writes.

The application owns the *active* head: the head checkpoint id lives in
``conversation_branches``, never in the saver's notion of the latest checkpoint.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Mapping

from sqlalchemy.orm import Session, sessionmaker

from noteagent.conversations.checkpoints import (
    CHECKPOINT_NS,
    CheckpointRuntime,
    checkpoint_id_of,
    thread_config,
    state_to_checkpoint,
)
from noteagent.conversations.models import ConversationBranch
from noteagent.conversations.records import (
    ConversationRecord,
    GraphState,
    MessageRecord,
    initial_state,
    record_from_ui,
    validate_state,
)
from noteagent.db.models import Conversation

logger = logging.getLogger(__name__)


class ConversationNotFound(KeyError):
    """Raised when a conversation id is unknown or malformed."""


@dataclass(slots=True)
class StateView:
    """One checkpoint's state plus the exact config it was read with."""

    values: GraphState
    config: dict[str, Any]


class ConversationService:
    """Reads and writes conversation state; owns where the active head points."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        runtime: CheckpointRuntime,
    ) -> None:
        self._session_factory = session_factory
        self._runtime = runtime

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
        checkpoint, new_versions = state_to_checkpoint(values)
        metadata = {
            "source": "update",
            "step": int(values.get("generation", 0) or 0),
            "parents": {CHECKPOINT_NS: parent_checkpoint_id} if parent_checkpoint_id else {},
        }
        saved = await self._runtime.saver.aput(
            thread_config(conversation_id), checkpoint, metadata, new_versions
        )
        new_id = checkpoint_id_of(saved)
        if publish:
            if branch_id is None:
                raise ValueError("publish requires a branch_id")
            self.publish_head(conversation_id, branch_id, new_id or "")
        return saved

    def publish_head(
        self, conversation_id: str, branch_id: str, checkpoint_id: str
    ) -> None:
        """Point one branch's head at a checkpoint and make it the active branch.

        Single application-DB transaction; the checkpoint was written to the saver
        beforehand, which is the compensating protocol, not one atomic transaction.
        """
        with self._session_factory() as session:
            conversation = self._load(session, conversation_id)
            branch = session.get(ConversationBranch, uuid.UUID(branch_id))
            if branch is None or str(branch.conversation_id) != str(conversation.id):
                raise ConversationNotFound(branch_id)
            branch.head_checkpoint_id = checkpoint_id
            conversation.active_branch_id = branch.id
            session.commit()
            logger.info(
                "published conversation=%s branch=%s head=%s",
                conversation_id,
                branch_id,
                checkpoint_id,
            )

    async def list_messages(self, conversation_id: str) -> list[MessageRecord] | None:
        """Project the active checkpoint's display history; None when unknown."""
        try:
            view = await self.get_state(conversation_id)
        except ConversationNotFound:
            return None
        return [record_from_ui(item) for item in view.values.get("ui_messages", [])]

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
    )
