"""Recovery subsystem DTOs shared by the gate, planner, coordinator and HTTP layer."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


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
