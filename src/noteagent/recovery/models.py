"""Durable journals for the recovery subsystem.

These tables are the persistent ledger the plan requires: workspace sequence and
maintenance state, one row per durable note mutation, preview/恢复 jobs, and the
per-path index repair records. They sit beside the checkpoint tables; nothing here
re-implements the saver or the notes repository.
"""

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

from noteagent.db.models import Base


def _utcnow() -> datetime:
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
