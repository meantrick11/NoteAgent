"""Formal note change journal records."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, Integer, JSON, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from NoteAgent.TechnicalSupport.DatabaseAccess.OrmBase import Base

def _utcnow() -> datetime:
    """UTC timestamp used by durable record defaults."""
    return datetime.now(timezone.utc)


class MutationRecord(Base):
    """One durable note mutation, keyed by an idempotent operation id."""

    __tablename__ = "mutation_records"
    __table_args__ = (
        Index("ix_mutation_records_conversation", "conversation_id"),
        Index("ix_mutation_records_after_commit", "after_commit"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    operation_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    # conversation / library / external
    origin_kind: Mapped[str] = mapped_column(Text, nullable=False)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    run_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    # create/write/append/replace/delete/move/folder
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    paths: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    before_hashes: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    before_commit: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_commit: Mapped[str | None] = mapped_column(Text, nullable=True)
    workspace_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="applied")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
