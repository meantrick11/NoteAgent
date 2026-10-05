"""Durable note-operation journal and atomic workspace sequence updates."""

import hashlib
from sqlalchemy import select
from NoteAgent.BusinessModules.NoteStorage.ChangeJournal.NoteChangeModels import MutationRecord
from NoteAgent.TechnicalSupport.NoteAccessControl.NoteAccessModels import WorkspaceState


class MutationJournal:
    """Persist operation records against the same session factory as note mutations."""

    def __init__(self, session_factory, versions) -> None:
        self._session_factory = session_factory
        self._versions = versions

    def get(self, operation_id: str) -> dict | None:
        with self._session_factory() as session:
            row = session.scalar(
                select(MutationRecord).where(MutationRecord.operation_id == operation_id)
            )
            return _row_to_dict(row) if row is not None else None


    def upsert(self, operation_id, origin, command, before, parent, after, seq, status, paths):
        with self._session_factory() as session:
            row = session.scalar(
                select(MutationRecord).where(MutationRecord.operation_id == operation_id)
            )
            if row is None:
                row = MutationRecord(operation_id=operation_id)
                session.add(row)
            row.origin_kind = origin.kind
            row.conversation_id = _uuid(origin.conversation_id)
            row.branch_id = _uuid(origin.branch_id)
            row.run_id = origin.run_id
            row.kind = command.kind
            row.paths = list(paths)
            row.before_hashes = {path: _sha256(data) for path, data in before.items()}
            if parent:
                row.before_hashes.update({f + "/": "directory" for f in self._versions.folders(parent)})
            row.before_commit = parent
            row.after_commit = after
            row.workspace_seq = seq
            row.status = status
            if status == "writing" and origin.kind != "recovery":
                workspace = session.get(WorkspaceState, 1)
                if workspace.maintenance_job_id in (None, operation_id):
                    workspace.maintenance_job_id = operation_id
                    workspace.maintenance_kind = "mutation"
            session.commit()


    def set_status(self, operation_id, status, error=None, *, after_commit=None,
                       workspace_seq=None, paths=None):
        with self._session_factory() as session:
            row = session.scalar(
                select(MutationRecord).where(MutationRecord.operation_id == operation_id)
            )
            if row is None:
                return
            row.status = status
            workspace = session.get(WorkspaceState, 1)
            if status == "failed" and workspace.maintenance_job_id == operation_id:
                workspace.maintenance_job_id = None
                workspace.maintenance_kind = None
            if status == "applied":
                workspace = session.get(WorkspaceState, 1)
                workspace.seq += 1
                workspace.current_commit = after_commit
                row.workspace_seq = workspace.seq
                if workspace.maintenance_job_id == operation_id:
                    workspace.maintenance_job_id = None
                    workspace.maintenance_kind = None
                if row.origin_kind == "conversation" and (row.run_id or "").startswith("draft-"):
                    workspace.maintenance_job_id = operation_id
                    workspace.maintenance_kind = "approval"
            if error is not None:
                row.error = error[:500]
            if after_commit is not None:
                row.after_commit = after_commit
            if workspace_seq is not None:
                row.workspace_seq = workspace_seq
            if paths is not None:
                row.paths = list(paths)
            session.commit()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _uuid(value: str | None):
    import uuid

    if not value:
        return None
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError):
        return None


def _row_to_dict(row: MutationRecord) -> dict:
    return {
        "operation_id": row.operation_id,
        "kind": row.kind,
        "paths": list(row.paths or []),
        "before_commit": row.before_commit,
        "after_commit": row.after_commit,
        "workspace_seq": row.workspace_seq,
        "status": row.status,
    }
