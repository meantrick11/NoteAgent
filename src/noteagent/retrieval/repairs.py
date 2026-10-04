"""Durable, per-file RAG index repairs.

An index update is not atomic with the note write, so it is tracked in the
``index_repairs`` ledger: a path is marked ``pending`` *before* any vector change and
becomes ``ready`` only after the vectors were written and verified against the file's
current body hash and the service's config fingerprint. A failure keeps the task at
``failed`` (retryable) and :meth:`search_synced` refuses to return that path, so a
stale or partial vector set is never surfaced as a fresh answer.

Body hash rule: ``raw-bytes-sha256-v1`` — sha256 of the file's exact on-disk bytes.
Vector text rule: ``chunk-content-v1`` — vectors are built from ``chunker.split`` of the
note text (see :class:`RetrievalService.index_note`); an empty/whitespace note is a
legal zero-chunk document and is "synced" when the ledger matches, not when it is
merely ``is_indexed``.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from noteagent.notes.repository import FileNoteRepository
from noteagent.recovery.models import IndexRepair
from noteagent.retrieval.models import SearchHit

logger = logging.getLogger(__name__)

BODY_HASH_RULE = "raw-bytes-sha256-v1"
VECTOR_TEXT_RULE = "chunk-content-v1"

PENDING = "pending"
READY = "ready"
FAILED = "failed"


@dataclass(slots=True)
class RepairStatus:
    """One path's repair outcome."""

    path: str
    status: str
    body_hash: str | None
    fingerprint: str | None
    synced: bool
    error: str | None = None


class IndexRepairService:
    """Ledger-backed per-file index maintenance."""

    def __init__(self, session_factory: sessionmaker[Session], notes: FileNoteRepository) -> None:
        self._session_factory = session_factory
        self._notes = notes

    # ---- body hashing -----------------------------------------------------

    def body_hash(self, path: str) -> str | None:
        """sha256 of the file's current bytes, or None when it no longer exists."""
        try:
            return hashlib.sha256(self._notes.path_of(path).read_bytes()).hexdigest()
        except (OSError, ValueError):
            return None

    # ---- ledger -----------------------------------------------------------

    def status(self, path: str) -> dict | None:
        with self._session_factory() as session:
            row = session.scalar(select(IndexRepair).where(IndexRepair.path == path))
            return _row_dict(row) if row is not None else None

    def unsynced_paths(self) -> list[str]:
        """Every path whose ledger is not ``ready`` (pending or failed)."""
        with self._session_factory() as session:
            rows = session.scalars(
                select(IndexRepair).where(IndexRepair.status.in_((PENDING, FAILED)))
            )
            return [row.path for row in rows]

    def _mark(self, path, status, *, body_hash=None, fingerprint=None, operation_id=None,
              error=None, attempts=None) -> None:
        with self._session_factory() as session:
            row = session.scalar(select(IndexRepair).where(IndexRepair.path == path))
            if row is None:
                row = IndexRepair(path=path)
                session.add(row)
            row.status = status
            row.body_hash = body_hash
            row.fingerprint = fingerprint
            if operation_id is not None:
                row.operation_id = operation_id
            row.error = (error or "")[:500] or None
            row.attempts = (attempts if attempts is not None else int(row.attempts or 0) + 1)
            session.commit()

    # ---- repair -----------------------------------------------------------

    def repair(self, path: str, retrieval, *, operation_id: str) -> RepairStatus:
        """Bring one path's vectors in line with the current file, durably."""
        fingerprint = _safe_fingerprint(retrieval)
        current_hash = self.body_hash(path)
        # Persist the pending intent before touching any vector.
        self._mark(path, PENDING, body_hash=current_hash, fingerprint=fingerprint,
                   operation_id=operation_id)
        try:
            retrieval.delete_note(path)
            if current_hash is not None:
                retrieval.index_note(path)
                if not retrieval.is_indexed(path):
                    # Empty/whitespace documents are legal zero-chunk results.
                    if not _is_empty(self._notes, path):
                        raise RuntimeError("index wrote no vectors for a non-empty note")
            self._mark(path, READY, body_hash=current_hash, fingerprint=fingerprint,
                       operation_id=operation_id)
            return RepairStatus(path, READY, current_hash, fingerprint, True)
        except Exception as exc:  # noqa: BLE001 - failure keeps the repair task
            logger.exception("index repair failed path=%s", path)
            self._mark(path, FAILED, body_hash=current_hash, fingerprint=fingerprint,
                       operation_id=operation_id, error=str(exc))
            return RepairStatus(path, FAILED, current_hash, fingerprint, False, str(exc))

    def repair_many(self, paths: list[str], retrieval, *, operation_id: str) -> list[RepairStatus]:
        return [self.repair(path, retrieval, operation_id=operation_id) for path in paths]

    def reconcile(self, retrieval, *, operation_id: str = "reconcile") -> list[RepairStatus]:
        """Retry every unsynced path (startup and explicit repair use the same op)."""
        return self.repair_many(self.unsynced_paths(), retrieval, operation_id=operation_id)

    # ---- sync checks and search fencing -----------------------------------

    def is_synced(self, path: str, retrieval) -> bool:
        """True when the ledger, the file bytes and the live vectors all agree."""
        row = self.status(path)
        if row is None or row["status"] != READY:
            return False
        if row["fingerprint"] != _safe_fingerprint(retrieval):
            return False
        current = self.body_hash(path)
        if row["body_hash"] != current:
            return False
        if current is None:
            return True  # file gone: ledger says ready, nothing to serve
        if _is_empty(self._notes, path):
            return not retrieval.is_indexed(path)
        return retrieval.is_indexed(path)

    def search_synced(self, retrieval, query: str, top_k: int = 3) -> list[SearchHit]:
        """Search but drop any hit whose file is not currently in sync."""
        hits = retrieval.search(query, top_k=max(top_k * 2, top_k))
        kept = [
            hit for hit in hits
            if self.is_synced(str((hit.metadata or {}).get("file_name") or ""), retrieval)
        ]
        return kept[:top_k]


def _safe_fingerprint(retrieval) -> str | None:
    try:
        return retrieval.config_fingerprint()
    except Exception:  # noqa: BLE001 - a retrieval without a fingerprint is simply unsynced
        return None


def _is_empty(notes: FileNoteRepository, path: str) -> bool:
    try:
        return not notes.read(path).strip()
    except (OSError, ValueError):
        return True


def _row_dict(row: IndexRepair) -> dict:
    return {
        "path": row.path,
        "status": row.status,
        "body_hash": row.body_hash,
        "fingerprint": row.fingerprint,
        "operation_id": row.operation_id,
        "attempts": row.attempts,
        "error": row.error,
    }
