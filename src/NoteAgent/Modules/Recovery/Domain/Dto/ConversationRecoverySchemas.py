"""Recovery subsystem DTOs shared by the gate, planner, coordinator and HTTP layer."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class PreviewIn(BaseModel):
    """Body for POST /conversations/{id}/recoveries/preview."""

    message_id: str
    edited_content: str
    expected_revision: int | None = None


class PreviewOut(BaseModel):
    """A pure preview plan; nothing has changed yet."""

    preview_id: str
    conversation_id: str
    can_apply: bool
    requires_confirmation: bool
    file_changes: list[dict]
    folder_changes: list[dict]
    conflicts: list[dict]
    affected_messages: list[str]
    state_revision: int
    workspace_seq: int
    content_digest: str
    expires_at: str | None = None


class RecoveryStartIn(BaseModel):
    """Body for POST /conversations/{id}/recoveries."""

    preview_id: str
    edited_content: str
    confirmed_file_changes: list[str] = []
    operation_id: str


class RecoveryRetryIn(BaseModel):
    """Body for POST /recoveries/{job_id}/retry."""

    operation_id: str


class JobOut(BaseModel):
    """Durable recovery job state returned to the client."""

    job_id: str
    operation_id: str
    conversation_id: str
    status: str
    stage: str | None = None
    prepared_turn_id: str | None = None
    error: str | None = None
    retryable: bool = True
    plan: dict = {}


class WorkspaceStatusOut(BaseModel):
    """Current workspace sequence, commit and maintenance state."""

    seq: int
    current_commit: str | None = None
    maintenance_job_id: str | None = None
    maintenance_kind: str | None = None


class MutationOut(BaseModel):
    """One ledger entry, as returned for diagnostics."""

    operation_id: str
    origin_kind: str
    kind: str
    paths: list[str]
    before_commit: str | None = None
    after_commit: str | None = None
    workspace_seq: int
    status: str
    created_at: datetime
