"""Shared access and durable maintenance state."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from NoteAgent.TechnicalSupport.DatabaseAccess.OrmBase import Base

def _utcnow() -> datetime:
    """UTC timestamp used by durable record defaults."""
    return datetime.now(timezone.utc)


class WorkspaceState(Base):
    """Singleton row: the current workspace sequence, commit and maintenance state."""

    __tablename__ = "workspace_state"

    # Fixed primary key: there is exactly one workspace per deployment.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_commit: Mapped[str | None] = mapped_column(Text, nullable=True)
    maintenance_job_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    maintenance_kind: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
