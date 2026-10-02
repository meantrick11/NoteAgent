"""ORM tables that track branches, runs, and recovery boundaries.

These sit beside the LangGraph checkpoint tables the saver owns; this module never
re-implements them. ``Base`` always comes from :mod:`noteagent.db.models`.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from noteagent.db.models import Base


def _utcnow() -> datetime:
    """Return the current UTC time for timestamp column defaults."""
    return datetime.now(timezone.utc)


class ConversationBranch(Base):
    """One logical conversation branch; its head pins the active checkpoint."""

    __tablename__ = "conversation_branches"
    __table_args__ = (
        Index("ix_conversation_branches_conversation", "conversation_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    parent_branch_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversation_branches.id", ondelete="SET NULL"), nullable=True
    )
    # Checkpoint this branch forked from; NULL for a root branch.
    fork_checkpoint_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    head_checkpoint_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    checkpoint_ns: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )


class ConversationRun(Base):
    """One prepared turn's execution claim, so a turn runs at most once."""

    __tablename__ = "conversation_runs"
    __table_args__ = (
        UniqueConstraint("request_id", name="uq_conversation_runs_request"),
        Index("ix_conversation_runs_conversation", "conversation_id"),
        Index(
            "uq_conversation_runs_active", "conversation_id", unique=True,
            postgresql_where=text("status IN ('prepared', 'running', 'interrupted')"),
            sqlite_where=text("status IN ('prepared', 'running', 'interrupted')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversation_branches.id", ondelete="SET NULL"), nullable=True
    )
    turn_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    user_message_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    checkpoint_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    accepted_checkpoint_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    lease_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="prepared")
    request_id: Mapped[str] = mapped_column(Text, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )


class UserMessageBoundary(Base):
    """The safe checkpoint captured just before one user message was accepted."""

    __tablename__ = "user_message_boundaries"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            "branch_id",
            "message_id",
            name="uq_user_message_boundaries_message",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversation_branches.id", ondelete="CASCADE"), nullable=False
    )
    message_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    turn_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    # Explicit before-config: never resolve a boundary through the saver's "latest".
    before_checkpoint_ns: Mapped[str] = mapped_column(
        Text, nullable=False, default=""
    )
    before_checkpoint_id: Mapped[str] = mapped_column(Text, nullable=False)
    workspace_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recoverable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
