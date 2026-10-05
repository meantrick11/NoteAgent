"""Per-file index repair records owned by retrieval."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    Integer,
    JSON,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from NoteAgent.TechnicalSupport.DatabaseAccess.OrmBase import Base




def _utcnow() -> datetime:
    """UTC timestamp used by durable record defaults."""
    return datetime.now(timezone.utc)


class IndexRepair(Base):
    """Per-path index repair record: body hash + config fingerprint + status."""

    __tablename__ = "index_repairs"
    __table_args__ = (
        Index("ix_index_repairs_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    body_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    fingerprint: Mapped[str | None] = mapped_column(Text, nullable=True)
    # pending / ready / failed / deleting
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    operation_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
