"""The single durable write path for notes.

Every formal note change (Library, chat draft approval, imports) goes through
:meth:`NoteMutationService.apply`, which records the operation and its recoverable
before-bytes *first*, writes the disk through the repository, commits a shadow Git
version, advances the workspace sequence, and only then reports success. A Git
failure restores the before-bytes; a Git success followed by a DB failure is
finished on retry from the retained operation ref without rewriting the disk.
"""

from __future__ import annotations

import hashlib
import logging
from contextlib import nullcontext
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from noteagent.notes.repository import FileNoteRepository
from noteagent.notes.versions import NoteVersionError, NoteVersionStore
from noteagent.recovery.gate import WorkspaceGate
from noteagent.recovery.models import MutationRecord

logger = logging.getLogger(__name__)

# Command kinds. One create + body is a single logical operation.
CREATE = "create"
WRITE = "write"          # append or replace (append flag)
DELETE = "delete"
MOVE = "move"
FOLDER_CREATE = "folder_create"
FOLDER_RENAME = "folder_rename"
FOLDER_DELETE = "folder_delete"
# Recovery-only raw-bytes restore; never produced by a normal caller command.
RECOVERY = "recovery"
KINDS = {CREATE, WRITE, DELETE, MOVE, FOLDER_CREATE, FOLDER_RENAME, FOLDER_DELETE}


def _safe_folder(name: str) -> str:
    """Return a one-level folder name; reject traversal and absolute paths."""
    raw = str(name).replace("\\", "/").strip().strip("/")
    parts = raw.split("/")
    if not raw or any(part in ("", ".", "..") for part in parts):
        raise MutationError(f"unsafe folder: {name!r}")
    return raw


class MutationError(RuntimeError):
    """Base class for durable-write failures."""


class HistoryUnavailable(MutationError):
    """The shadow Git store is missing; a write without history is not allowed."""


class ConflictError(MutationError):
    """A caller's expected base hash no longer matches the disk."""


class GitFailure(MutationError):
    """The disk was written but the version commit failed and was rolled back."""


@dataclass(slots=True)
class Origin:
    """Where a mutation came from, for attribution in the ledger."""

    kind: str
    conversation_id: str | None = None
    branch_id: str | None = None
    run_id: str | None = None

    @classmethod
    def library(cls) -> "Origin":
        return cls(kind="library")

    @classmethod
    def external(cls) -> "Origin":
        return cls(kind="external")


@dataclass(slots=True)
class MutationCommand:
    """One requested change, independent of who asked for it."""

    kind: str
    file_name: str | None = None
    dest: str | None = None
    content: str = ""
    title: str | None = None
    name: str | None = None
    append: bool = True


@dataclass(slots=True)
class MutationResult:
    """The outcome recorded in the ledger and returned to the caller."""

    operation_id: str
    kind: str
    paths: list[str] = field(default_factory=list)
    commit: str | None = None
    workspace_seq: int = 0
    indexed: bool = False
    reused: bool = False
    applied: bool = True


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class NoteMutationService:
    """Coordinates notes, the shadow Git store, the workspace gate and the ledger."""

    def __init__(
        self,
        notes: FileNoteRepository,
        versions: NoteVersionStore,
        gate: WorkspaceGate,
        session_factory: sessionmaker[Session],
        repairs=None,
    ) -> None:
        self._notes = notes
        self._versions = versions
        self._gate = gate
        self._session_factory = session_factory
        self._repairs = repairs

    # ---- public API -------------------------------------------------------

    def apply(
        self,
        command: MutationCommand,
        origin: Origin,
        operation_id: str,
        *,
        expected_hashes: dict[str, str] | None = None,
        retrieval: Any | None = None,
    ) -> MutationResult:
        """Apply one operation idempotently and durably."""
        if command.kind not in KINDS:
            raise MutationError(f"unknown mutation kind: {command.kind!r}")
        existing = self._ledger_get(operation_id)
        if existing is not None and existing["status"] == "applied":
            return self._from_ledger(existing)

        before = self._read_before(command)
        if expected_hashes:
            self._check_expected(before, expected_hashes)
        paths = sorted(before)

        parent = self._gate.state().current_commit
        # Git already accepted this operation (crash between commit and ledger):
        # finish the ledger and never touch the disk again.
        retained = self._versions.resolve_ref(operation_id)
        if retained is not None and existing is None:
            seq = self._gate.advance(current_commit=retained)
            self._ledger_upsert(
                operation_id, origin, command, before, parent, retained, seq, "applied", paths
            )
            return MutationResult(operation_id, command.kind, paths, retained, seq)

        if existing is None:
            self._ledger_upsert(
                operation_id, origin, command, before, parent, None, 0, "writing", paths
            )

        with self._gate.operation("mutate"):
            try:
                self._apply_disk(command)
            except Exception as exc:
                self._restore(before)
                self._ledger_status(operation_id, "failed", str(exc))
                raise
            try:
                snapshot = self._versions.snapshot(parent, operation_id)
            except Exception as exc:
                self._restore(before)
                self._ledger_status(operation_id, "failed", str(exc))
                raise GitFailure(f"version commit failed: {exc}") from exc
            seq = self._gate.advance(current_commit=snapshot.commit)
            self._ledger_status(
                operation_id, "applied",
                after_commit=snapshot.commit, workspace_seq=seq,
                paths=list(snapshot.changed_paths or paths),
            )
            indexed = self._sync_index(command, retrieval, operation_id, before)

        logger.info(
            "note mutation op=%s kind=%s commit=%s seq=%s paths=%s",
            operation_id, command.kind, snapshot.commit, seq, paths,
        )
        return MutationResult(
            operation_id, command.kind, list(snapshot.changed_paths or paths),
            snapshot.commit, seq, indexed, reused=snapshot.reused,
        )

    def restore(
        self,
        *,
        restores: dict[str, bytes],
        deletes: list[str],
        folders_create: list[str],
        folders_delete: list[str],
        origin: Origin,
        operation_id: str,
        lock: bool = True,
    ) -> MutationResult:
        """Recovery-only: write raw target bytes / delete paths as one commit.

        Bytes are written as-is (never re-encoded), so a rollback restores the exact
        on-disk content. Folders are only touched by the manifest: a removed folder is
        rmdir'd only when empty, so other sessions' files are always preserved.
        """
        existing = self._ledger_get(operation_id)
        if existing is not None and existing["status"] == "applied":
            return self._from_ledger(existing)

        paths = sorted(set(restores) | set(deletes))
        before: dict[str, bytes] = {}
        for path in paths:
            try:
                before[path] = self._notes.path_of(path).read_bytes()
            except (OSError, ValueError):
                continue
        parent = self._gate.state().current_commit
        retained = self._versions.resolve_ref(operation_id)
        if retained is not None and existing is None:
            seq = self._gate.advance(current_commit=retained)
            self._ledger_upsert(
                operation_id, origin,
                MutationCommand(kind=RECOVERY, file_name=None), before, parent,
                retained, seq, "applied", paths,
            )
            return MutationResult(operation_id, RECOVERY, paths, retained, seq)

        if existing is None:
            self._ledger_upsert(
                operation_id, origin, MutationCommand(kind=RECOVERY, file_name=None),
                before, parent, None, 0, "writing", paths,
            )
        with (self._gate.operation("mutate") if lock else nullcontext()):
            try:
                for path, data in restores.items():
                    target = self._notes.path_of(path)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
                for path in deletes:
                    target = self._notes.path_of(path)
                    if target.exists():
                        target.unlink()
                for folder in folders_create:
                    (self._notes.root / _safe_folder(folder)).mkdir(parents=True, exist_ok=True)
                for folder in folders_delete:
                    target = self._notes.root / _safe_folder(folder)
                    if target.is_dir() and not any(target.iterdir()):
                        target.rmdir()
                snapshot = self._versions.snapshot(parent, operation_id)
            except GitFailure:
                raise
            except Exception as exc:
                self._restore(before)
                self._ledger_status(operation_id, "failed", str(exc))
                raise GitFailure(f"recovery commit failed: {exc}") from exc
            seq = self._gate.advance(current_commit=snapshot.commit)
            self._ledger_status(
                operation_id, "applied", after_commit=snapshot.commit,
                workspace_seq=seq, paths=list(snapshot.changed_paths or paths),
            )
        logger.info(
            "note restore op=%s commit=%s seq=%s restored=%d deleted=%d",
            operation_id, snapshot.commit, seq, len(restores), len(deletes),
        )
        return MutationResult(
            operation_id, RECOVERY, list(snapshot.changed_paths or paths),
            snapshot.commit, seq, True, reused=snapshot.reused,
        )

    def head_commit(self) -> str | None:
        """Current workspace commit, for a caller that wants a base hash."""
        return self._gate.state().current_commit

    def base_hashes(self, paths: list[str]) -> dict[str, str]:
        """sha256 of the current bytes for each path that exists."""
        out: dict[str, str] = {}
        for path in paths:
            try:
                out[path] = _sha256(self._notes.path_of(path).read_bytes())
            except (OSError, ValueError, NoteVersionError):
                continue
        return out

    # ---- disk -------------------------------------------------------------

    def _affected_paths(self, command: MutationCommand) -> list[str]:
        if command.kind == CREATE:
            return [self._notes.normalize(command.file_name or "")]
        if command.kind == WRITE:
            return [self._notes.normalize(command.file_name or "")]
        if command.kind == DELETE:
            return [self._notes.normalize(command.file_name or "")]
        if command.kind == MOVE:
            return [self._notes.normalize(command.file_name or ""),
                    self._notes.normalize(command.dest or "")]
        if command.kind == FOLDER_CREATE:
            return [f"{self._notes.normalize(command.name or '')}/"]
        if command.kind == FOLDER_RENAME:
            folder = self._notes.normalize(command.name or "")
            dest = self._notes.normalize(command.dest or "")
            return [f"{folder}/", f"{dest}/"]
        # folder_delete
        folder = self._notes.normalize(command.name or "")
        return [f"{folder}/"]

    def _read_before(self, command: MutationCommand) -> dict[str, bytes]:
        before: dict[str, bytes] = {}
        if command.kind == FOLDER_DELETE:
            prefix = f"{self._notes.normalize(command.name or '')}/"
            for name in self._notes.list_notes():
                if name.startswith(prefix):
                    before[name] = self._notes.path_of(name).read_bytes()
            return before
        for path in self._affected_paths(command):
            if path.endswith("/"):
                continue
            try:
                before[path] = self._notes.path_of(path).read_bytes()
            except (OSError, ValueError):
                continue
        return before

    def _apply_disk(self, command: MutationCommand) -> None:
        notes = self._notes
        if command.kind == CREATE:
            name = notes.normalize(command.file_name or "")
            notes.create(name, command.title or name.rsplit("/", 1)[-1].removesuffix(".md"))
            if command.content:
                notes.write(name, command.content, append=True)
            return
        if command.kind == WRITE:
            notes.write(
                notes.normalize(command.file_name or ""),
                command.content, append=command.append,
            )
            return
        if command.kind == DELETE:
            notes.delete(notes.normalize(command.file_name or ""))
            return
        if command.kind == MOVE:
            notes.move(command.file_name or "", command.dest or "")
            return
        if command.kind == FOLDER_CREATE:
            notes.create_folder(command.name or "")
            return
        if command.kind == FOLDER_RENAME:
            notes.rename_folder(command.name or "", command.dest or "")
            return
        if command.kind == FOLDER_DELETE:
            notes.delete_folder(command.name or "")
            return
        raise MutationError(f"unhandled kind: {command.kind}")

    def _restore(self, before: dict[str, bytes]) -> None:
        """Roll a half-applied disk change back to its before-bytes."""
        for path, data in before.items():
            try:
                target = self._notes.path_of(path)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            except Exception:  # best-effort; the ledger keeps the record
                logger.exception("note restore failed path=%s", path)

    def _index_paths(self, command: MutationCommand, before: dict[str, bytes]) -> list[str]:
        """Concrete note paths whose vectors must be brought in line."""
        notes = self._notes
        if command.kind == FOLDER_DELETE:
            return list(before)
        if command.kind == DELETE:
            return [notes.normalize(command.file_name or "")]
        if command.kind == MOVE:
            return [notes.normalize(command.file_name or ""), notes.normalize(command.dest or "")]
        if command.kind == FOLDER_RENAME:
            old = notes.normalize(command.name or "")
            new = notes.normalize(command.dest or "")
            return [n for n in notes.list_notes()
                    if n.startswith(f"{old}/") or n.startswith(f"{new}/")]
        if command.kind in (CREATE, WRITE):
            return [notes.normalize(command.file_name or "")]
        return []

    def _sync_index(self, command: MutationCommand, retrieval: Any | None,
                    operation_id: str, before: dict[str, bytes]) -> bool:
        """Update the vectors for the affected paths; durable when repairs is present."""
        if retrieval is None:
            return False
        paths = self._index_paths(command, before)
        if self._repairs is not None:
            statuses = self._repairs.repair_many(paths, retrieval, operation_id=operation_id)
            return all(status.synced for status in statuses)
        # Legacy best-effort path (no repair ledger available).
        try:
            if command.kind == DELETE:
                retrieval.delete_note(self._notes.normalize(command.file_name or ""))
                return False
            if command.kind in (MOVE, FOLDER_RENAME):
                src = self._notes.normalize(command.file_name or command.name or "")
                dest = self._notes.normalize(command.dest or "")
                try:
                    retrieval.delete_note(src)
                except Exception:
                    logger.exception("index delete failed path=%s", src)
                return bool(retrieval.index_note(dest))
            if command.kind == FOLDER_DELETE:
                for name in before:
                    retrieval.delete_note(name)
                return False
            target = self._notes.normalize(command.file_name or "")
            retrieval.index_note(target)
            return True
        except Exception:
            logger.exception("note index sync failed kind=%s", command.kind)
            return False

    # ---- validation -------------------------------------------------------

    def _check_expected(self, before: dict[str, bytes], expected: dict[str, str]) -> None:
        for path, digest in expected.items():
            current = before.get(path)
            if current is None:
                if digest not in ("", "missing"):
                    raise ConflictError(f"{path} is missing but a base hash was given")
                continue
            if _sha256(current) != digest:
                raise ConflictError(f"{path} changed since the base hash")

    # ---- ledger -----------------------------------------------------------

    def _ledger_get(self, operation_id: str) -> dict | None:
        with self._session_factory() as session:
            row = session.scalar(
                select(MutationRecord).where(MutationRecord.operation_id == operation_id)
            )
            return _row_to_dict(row) if row is not None else None

    def _ledger_upsert(self, operation_id, origin, command, before, parent, after, seq, status, paths):
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
            row.before_commit = parent
            row.after_commit = after
            row.workspace_seq = seq
            row.status = status
            session.commit()

    def _ledger_status(self, operation_id, status, error=None, *, after_commit=None,
                       workspace_seq=None, paths=None):
        with self._session_factory() as session:
            row = session.scalar(
                select(MutationRecord).where(MutationRecord.operation_id == operation_id)
            )
            if row is None:
                return
            row.status = status
            if error is not None:
                row.error = error[:500]
            if after_commit is not None:
                row.after_commit = after_commit
            if workspace_seq is not None:
                row.workspace_seq = workspace_seq
            if paths is not None:
                row.paths = list(paths)
            session.commit()

    def _from_ledger(self, row: dict) -> MutationResult:
        return MutationResult(
            operation_id=row["operation_id"], kind=row["kind"], paths=list(row["paths"]),
            commit=row["after_commit"], workspace_seq=row["workspace_seq"],
        )


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
        "after_commit": row.after_commit,
        "workspace_seq": row.workspace_seq,
        "status": row.status,
    }
