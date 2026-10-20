"""Persistent model configuration and capability records.

One row per model configuration; capabilities are a child table so enabling and
verification state have a single authoritative home.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from NoteAgent.Common.Database.OrmBase import Base


def utcnow() -> datetime:
    """Timezone-aware timestamp for model configuration rows."""
    return datetime.now(timezone.utc)


class ModelConfigRow(Base):
    """One model configuration, including its provider connection fields."""

    __tablename__ = "model_configs"
    __table_args__ = (
        # At most one active row; works on PostgreSQL and SQLite.
        Index(
            "ux_model_configs_active",
            "is_active",
            unique=True,
            postgresql_where=text("is_active"),
            sqlite_where=text("is_active"),
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    auth_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="api_key")
    api_key: Mapped[str] = mapped_column(Text, nullable=False, default="")
    timeout_s: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    context_window: Mapped[int] = mapped_column(Integer, nullable=False, default=32768)
    temperature: Mapped[float | None] = mapped_column(Float)
    max_tokens: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    capabilities: Mapped[list["ModelCapabilityRow"]] = relationship(
        back_populates="config",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ModelCapabilityRow(Base):
    """One capability record for one model configuration."""

    __tablename__ = "model_capabilities"

    model_id: Mapped[str] = mapped_column(
        ForeignKey("model_configs.id", ondelete="CASCADE"), primary_key=True
    )
    capability: Mapped[str] = mapped_column(String(32), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    verification: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    probe_version: Mapped[int | None] = mapped_column(Integer)
    evidence: Mapped[dict[str, object] | None] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    config: Mapped[ModelConfigRow] = relationship(back_populates="capabilities")
