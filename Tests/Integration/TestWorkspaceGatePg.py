"""Workspace gate: real PostgreSQL advisory locks and durable maintenance state.

Every case here uses a real schema and real connections, because the whole point of
the gate is cross-connection mutual exclusion and crash behaviour that an in-process
lock cannot demonstrate.
"""

from __future__ import annotations

import time

import psycopg
import pytest

from NoteAgent.TechnicalSupport.DatabaseAccess import Base, create_engine_from_url, create_session_factory, load_all_models
from NoteAgent.TechnicalSupport.NoteAccessControl.NoteAccessGate import LOCK_KEY, WorkspaceBusy, WorkspaceGate


def _gate(pg_target):
    load_all_models()
    engine = create_engine_from_url(pg_target.sqlalchemy_url)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    gate = WorkspaceGate(factory, libpq_dsn=pg_target.libpq_dsn)
    gate.ensure_row()
    return gate, factory, engine


def test_exclusive_blocks_other_modes(pg_target):
    gate, _, engine = _gate(pg_target)
    try:
        with gate.operation("mutate"):
            with pytest.raises(WorkspaceBusy):
                with gate.operation("mutate"):
                    pass
            with pytest.raises(WorkspaceBusy):
                with gate.operation("read"):
                    pass
    finally:
        engine.dispose()


def test_shared_shares_but_blocks_exclusive(pg_target):
    gate, _, engine = _gate(pg_target)
    try:
        with gate.operation("read"):
            with gate.operation("read"):  # shared + shared is fine
                pass
            with gate.operation("chat"):  # chat is shared too
                pass
            with pytest.raises(WorkspaceBusy):
                with gate.operation("recovery"):
                    pass
    finally:
        engine.dispose()


def test_busy_returns_without_blocking(pg_target):
    gate, _, engine = _gate(pg_target)
    try:
        with gate.operation("recovery"):
            started = time.monotonic()
            with pytest.raises(WorkspaceBusy):
                with gate.operation("model_rebuild"):
                    pass
            assert time.monotonic() - started < 2.0
    finally:
        engine.dispose()


def test_another_connection_cannot_unlock_a_valid_lock(pg_target):
    gate, _, engine = _gate(pg_target)
    try:
        with gate.operation("mutate"):
            foreign = psycopg.connect(pg_target.libpq_dsn, autocommit=True)
            try:
                released = foreign.execute(
                    "SELECT pg_advisory_unlock(%s)", (LOCK_KEY,)
                ).fetchone()[0]
            finally:
                foreign.close()
            assert released is False
            # Our lock is still held in force.
            with pytest.raises(WorkspaceBusy):
                with gate.operation("mutate"):
                    pass
    finally:
        engine.dispose()


def test_disconnect_releases_lock_but_maintenance_still_blocks(pg_target):
    gate, _, engine = _gate(pg_target)
    try:
        # Simulate a worker that died while holding the exclusive lock.
        session = gate.operation("mutate")
        session.__enter__()
        session._handle.close()  # abrupt disconnect -> advisory lock is freed
        session.__exit__(None, None, None)

        # The durable maintenance row is what keeps the workspace closed.
        gate.set_maintenance("job-1", "recovery")
        with pytest.raises(WorkspaceBusy):
            with gate.operation("mutate"):
                pass
        with pytest.raises(WorkspaceBusy):
            with gate.operation("read"):
                pass

        gate.clear_maintenance()
        with gate.operation("mutate"):
            pass
    finally:
        engine.dispose()


def test_sequence_advance_and_state_round_trip(pg_target):
    gate, _, engine = _gate(pg_target)
    try:
        first = gate.advance(current_commit="commit-a")
        second = gate.advance(current_commit="commit-b")
        assert second == first + 1
        state = gate.state()
        assert state.seq == second
        assert state.current_commit == "commit-b"
        assert gate.maintenance() is None
    finally:
        engine.dispose()
