"""Cross-process workspace gate and maintenance state.

Fixed acquisition order (never reversed): WorkspaceGate → model runtime lease →
conversation CAS → checkpoint IO. Reading and chatting share the gate; mutating,
recovering and rebuilding the index take it exclusively.

On PostgreSQL the gate is a session advisory lock on a dedicated connection, so it
is enforced across processes and is released automatically if the process dies.
Because the lock vanishing on a crash must not silently re-open writes, a *durable*
maintenance row keeps read/chat/write refused until the job finishes or a repair is
explicitly run. Non-PostgreSQL deployments (and unit tests) fall back to an
in-process reader/writer so shared/exclusive semantics still hold.
"""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from collections.abc import Iterator

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from noteagent.recovery.models import WorkspaceState

logger = logging.getLogger(__name__)

# int64 key shared by every process of one deployment ("NoteAgen").
LOCK_KEY = 0x4E6F74654167656E

SHARED_MODES = frozenset({"read", "chat"})
EXCLUSIVE_MODES = frozenset({"mutate", "recovery", "model_rebuild"})
ALL_MODES = SHARED_MODES | EXCLUSIVE_MODES


class WorkspaceBusy(RuntimeError):
    """Another operation holds the workspace, or maintenance is in force."""

    def __init__(self, message: str = "workspace is busy"):
        super().__init__(message)
        self.message = message


def is_postgres_url(database_url: str) -> bool:
    return database_url.startswith("postgresql")


class _LocalRW:
    """Non-blocking in-process reader/writer used when there is no advisory lock."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._readers = 0
        self._writer = False

    def acquire_shared(self) -> bool:
        with self._lock:
            if self._writer:
                return False
            self._readers += 1
            return True

    def acquire_exclusive(self) -> bool:
        with self._lock:
            if self._writer or self._readers:
                return False
            self._writer = True
            return True

    def release_shared(self) -> None:
        with self._lock:
            self._readers = max(0, self._readers - 1)

    def release_exclusive(self) -> None:
        with self._lock:
            self._writer = False


class WorkspaceGate:
    """Owns the process/DB-wide lock and the durable maintenance flag."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        libpq_dsn: str | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._dsn = libpq_dsn
        self._local = _LocalRW()

    # ---- maintenance (durable) -------------------------------------------

    def ensure_row(self) -> None:
        """Create the singleton workspace row when the deployment has none."""
        with self._session_factory() as session:
            if session.get(WorkspaceState, 1) is None:
                session.add(WorkspaceState(id=1, seq=0, current_commit=None))
                session.commit()

    def maintenance(self) -> tuple[str, str] | None:
        """(job_id, kind) while a failed/interrupted recovery blocks the workspace."""
        with self._session_factory() as session:
            row = session.get(WorkspaceState, 1)
            if row is None or row.maintenance_job_id is None:
                return None
            return row.maintenance_job_id, row.maintenance_kind or ""

    def set_maintenance(self, job_id: str, kind: str) -> None:
        with self._session_factory() as session:
            self._ensure_row(session)
            session.execute(update(WorkspaceState).where(WorkspaceState.id == 1).values(
                maintenance_job_id=job_id, maintenance_kind=kind,
            ))
            session.commit()

    def clear_maintenance(self) -> None:
        with self._session_factory() as session:
            self._ensure_row(session)
            session.execute(update(WorkspaceState).where(WorkspaceState.id == 1).values(
                maintenance_job_id=None, maintenance_kind=None,
            ))
            session.commit()

    def state(self) -> WorkspaceState:
        """A detached snapshot of the workspace row."""
        with self._session_factory() as session:
            self._ensure_row(session)
            row = session.get(WorkspaceState, 1)
            assert row is not None
            session.expunge(row)
            return row

    def advance(self, *, current_commit: str) -> int:
        """Bump the workspace sequence and record the commit; returns the new seq."""
        with self._session_factory() as session:
            self._ensure_row(session)
            row = session.get(WorkspaceState, 1)
            assert row is not None
            row.seq = int(row.seq or 0) + 1
            row.current_commit = current_commit
            session.commit()
            return row.seq

    # ---- gate --------------------------------------------------------------

    def operation(self, mode: str) -> "_GateSession":
        """Hold the gate in ``mode`` for the duration of a with-block."""
        if mode not in ALL_MODES:
            raise ValueError(f"unknown workspace mode: {mode!r}")
        return _GateSession(self, mode)

    def _acquire(self, mode: str):
        """Take the lock; returns the backend handle to release later."""
        handle = self._acquire_postgres(mode) if self._dsn else self._acquire_local(mode)
        # The lock is held; now enforce the durable maintenance flag for every
        # gated mode (read/chat/mutate/recovery/model_rebuild).
        if self.maintenance() is not None:
            self._release(mode, handle)
            raise WorkspaceBusy(
                "workspace is in maintenance; only repair and status are available"
            )
        return handle

    def _release(self, mode: str, handle) -> None:
        if handle is None:
            if mode in SHARED_MODES:
                self._local.release_shared()
            else:
                self._local.release_exclusive()
        else:
            handle.close()

    def _acquire_local(self, mode: str):
        ok = (self._local.acquire_shared() if mode in SHARED_MODES
              else self._local.acquire_exclusive())
        if not ok:
            raise WorkspaceBusy(f"workspace is busy for mode={mode}")
        return None

    def _acquire_postgres(self, mode: str):
        import psycopg

        connection = psycopg.connect(self._dsn, autocommit=True)
        try:
            function = "pg_try_advisory_lock_shared" if mode in SHARED_MODES else "pg_try_advisory_lock"
            acquired = connection.execute(
                f"SELECT {function}(%s)", (LOCK_KEY,)
            ).fetchone()[0]
        except Exception:
            connection.close()
            raise
        if not acquired:
            connection.close()
            raise WorkspaceBusy(f"workspace is busy for mode={mode}")
        return connection

    def _ensure_row(self, session: Session) -> None:
        if session.get(WorkspaceState, 1) is None:
            session.add(WorkspaceState(id=1, seq=0, current_commit=None))


class _GateSession:
    """Context manager (sync and async) wrapping one gate acquisition."""

    def __init__(self, gate: WorkspaceGate, mode: str) -> None:
        self._gate = gate
        self._mode = mode
        self._handle = None
        self._acquired = False

    def __enter__(self) -> "_GateSession":
        self._handle = self._gate._acquire(self._mode)
        self._acquired = True
        return self

    def __exit__(self, *exc) -> None:
        if self._acquired:
            self._gate._release(self._mode, self._handle)
            self._acquired = False
            self._handle = None

    async def __aenter__(self) -> "_GateSession":
        return self.__enter__()

    async def __aexit__(self, *exc) -> None:
        self.__exit__(*exc)


@contextmanager
def guarded(gate: WorkspaceGate, mode: str) -> Iterator[None]:
    """Sync sugar: ``with guarded(gate, "mutate"): ...``."""
    with gate.operation(mode):
        yield
