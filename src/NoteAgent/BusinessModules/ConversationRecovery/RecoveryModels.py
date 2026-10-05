"""Conversation recovery preview and job records."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Index, Integer, JSON, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from NoteAgent.TechnicalSupport.DatabaseAccess.OrmBase import Base

def _utcnow() -> datetime:
    """UTC timestamp used by durable record defaults."""
    return datetime.now(timezone.utc)


class RecoveryPreview(Base):
    """A pure preview plan a user must confirm before a recovery starts."""

    __tablename__ = "recovery_previews"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    message_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    expected_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    plan: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RecoveryJob(Base):
    """A recovery job's durable state machine row."""

    __tablename__ = "recovery_jobs"
    __table_args__ = (
        Index("ix_recovery_jobs_conversation", "conversation_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    operation_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    message_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    preview_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="prepared")
    stage: Mapped[str | None] = mapped_column(Text, nullable=True)
    plan: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    candidate_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    edited_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmed_paths: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    prepared_turn_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_paths: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    retryable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
