"""The unified durable write path: idempotency, conflicts, rollback and recovery."""

from __future__ import annotations

import pytest

from noteagent.db import Base, create_engine_from_url, create_session_factory, load_all_models
from noteagent.notes.mutations import (
    CREATE,
    DELETE,
    FOLDER_CREATE,
    MOVE,
    WRITE,
    ConflictError,
    GitFailure,
    MutationCommand,
    NoteMutationService,
    Origin,
)
from noteagent.notes.repository import FileNoteRepository
from noteagent.notes.versions import NoteVersionStore
from noteagent.recovery.gate import WorkspaceGate
from noteagent.recovery.models import MutationRecord


@pytest.fixture
def env(tmp_path):
    notes = FileNoteRepository(tmp_path / "notes")
    versions = NoteVersionStore(tmp_path / "history", notes.root)
    load_all_models()
    engine = create_engine_from_url("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    gate = WorkspaceGate(factory)
    gate.ensure_row()
    service = NoteMutationService(notes, versions, gate, factory)
    return service, notes, versions, gate, factory


def _ledger(factory, operation_id):
    from sqlalchemy import select
    with factory() as session:
        return session.scalar(select(MutationRecord).where(MutationRecord.operation_id == operation_id))


def test_worker_death_before_git_keeps_gate_closed_until_compensation(env, monkeypatch):
    from noteagent.recovery.gate import WorkspaceBusy
    service, notes, versions, gate, _ = env
    service.initialize_locked()
    def terminate(*args, **kwargs):
        raise KeyboardInterrupt('worker killed')
    monkeypatch.setattr(versions, 'snapshot', terminate)
    with pytest.raises(KeyboardInterrupt):
        service.apply(MutationCommand(kind=CREATE, file_name='A.md'), Origin.library(), 'crashed')
    assert gate.maintenance() == ('crashed', 'mutation')
    with pytest.raises(WorkspaceBusy):
        service.apply(MutationCommand(kind=CREATE, file_name='B.md'), Origin.library(), 'later')
    service.reconcile_pending()
    assert not notes.exists('A.md')
    assert gate.maintenance() is None


def test_create_write_move_delete_are_ledgered(env):
    service, notes, versions, gate, factory = env
    created = service.apply(
        MutationCommand(kind=CREATE, file_name="A.md", title="A", content="最初正文\n"),
        Origin.library(), "op-create",
    )
    assert created.commit and created.paths == ["A.md"]
    assert notes.read("A.md") == "# A\n\n最初正文\n"
    assert versions.read_blob(created.commit, "A.md") == notes.path_of("A.md").read_bytes()

    written = service.apply(
        MutationCommand(kind=WRITE, file_name="A.md", content="追加", append=True),
        Origin.library(), "op-write",
    )
    assert written.commit != created.commit
    assert "追加" in notes.read("A.md")

    notes.move  # noqa: B018 - silence unused import check for MOVE branch below
    moved = service.apply(
        MutationCommand(kind=MOVE, file_name="A.md", dest="B.md"),
        Origin.library(), "op-move",
    )
    assert set(moved.paths) >= {"A.md", "B.md"}
    assert notes.exists("B.md") and not notes.exists("A.md")

    service.apply(MutationCommand(kind=DELETE, file_name="B.md"), Origin.library(), "op-delete")
    assert not notes.exists("B.md")
    row = _ledger(factory, "op-create")
    assert row is not None and row.status == "applied"
    assert row.origin_kind == "library"
    assert row.after_commit == created.commit


def test_folder_create_is_recorded(env):
    service, notes, versions, gate, factory = env
    result = service.apply(
        MutationCommand(kind=FOLDER_CREATE, name="Python"), Origin.library(), "op-folder"
    )
    assert notes.list_folders() == ["Python"]
    assert result.commit is not None


def test_duplicate_operation_is_idempotent(env):
    service, notes, versions, gate, factory = env
    service.apply(
        MutationCommand(kind=CREATE, file_name="A.md", title="A", content="one\n"),
        Origin.library(), "op-1",
    )
    again = service.apply(
        MutationCommand(kind=WRITE, file_name="A.md", content="two", append=True),
        Origin.library(), "op-1",
    )
    # Same operation id returns the original result and never appends twice.
    assert "two" not in notes.read("A.md")
    assert again.commit == _ledger(factory, "op-1").after_commit


def test_expected_hash_mismatch_is_refused(env):
    service, notes, versions, gate, factory = env
    service.apply(
        MutationCommand(kind=CREATE, file_name="A.md", title="A", content="base\n"),
        Origin.library(), "op-base",
    )
    with pytest.raises(ConflictError):
        service.apply(
            MutationCommand(kind=WRITE, file_name="A.md", content="x", append=True),
            Origin.library(), "op-conflict",
            expected_hashes={"A.md": "0" * 64},
        )
    assert "x" not in notes.read("A.md")


def test_git_failure_restores_before_bytes(env, monkeypatch):
    service, notes, versions, gate, factory = env
    service.apply(
        MutationCommand(kind=CREATE, file_name="A.md", title="A", content="original\n"),
        Origin.library(), "op-base",
    )
    original = notes.path_of("A.md").read_bytes()

    def boom(*args, **kwargs):
        raise RuntimeError("git exploded")

    monkeypatch.setattr(versions, "snapshot", boom)
    with pytest.raises(GitFailure):
        service.apply(
            MutationCommand(kind=WRITE, file_name="A.md", content="half-written", append=True),
            Origin.library(), "op-gitfail",
        )
    # The disk matches the pre-operation bytes and the ledger records the failure.
    assert notes.path_of("A.md").read_bytes() == original
    assert _ledger(factory, "op-gitfail").status == "failed"


def test_git_committed_but_ledger_missing_recovers_without_rewrite(env):
    service, notes, versions, gate, factory = env
    # Simulate a crash after Git accepted the commit but before the ledger row existed.
    notes.create("A.md", "A")
    notes.write("A.md", "committed body\n", append=False)
    commit = versions.snapshot(None, "op-crash").commit
    assert versions.resolve_ref("op-crash") == commit

    result = service.apply(
        MutationCommand(kind=CREATE, file_name="A.md", title="A", content="would duplicate"),
        Origin.library(), "op-crash",
    )
    # Finished from the retained ref: no rewrite, no duplicate create.
    assert result.commit == commit
    assert b"committed body" in notes.path_of("A.md").read_bytes()
    # The disk still matches the committed blob, proving the retry did not rewrite it.
    assert notes.path_of("A.md").read_bytes() == versions.read_blob(commit, "A.md")
    assert _ledger(factory, "op-crash").status == "applied"


def test_conversation_origin_is_attributed(env):
    service, notes, versions, gate, factory = env
    origin = Origin(kind="conversation", conversation_id=None, branch_id=None, run_id="run-9")
    service.apply(
        MutationCommand(kind=CREATE, file_name="C.md", title="C", content="x\n"),
        origin, "op-conv",
    )
    row = _ledger(factory, "op-conv")
    assert row.origin_kind == "conversation" and row.run_id == "run-9"


@pytest.mark.parametrize("kind", [CREATE, MOVE, "folder_rename"])
def test_git_failure_restores_absence_and_folders(env, monkeypatch, kind):
    service, notes, versions, gate, factory = env
    service.apply(MutationCommand(kind=CREATE, file_name="Old/A.md", content="base"), Origin.library(), "base")
    before = {p.relative_to(notes.root).as_posix(): p.read_bytes() for p in notes.root.rglob("*.md")}
    folders = notes.list_folders()
    def boom(*args, **kwargs): raise RuntimeError("git failed")
    monkeypatch.setattr(versions, "snapshot", boom)
    command = {CREATE: MutationCommand(kind=CREATE, file_name="New.md"), MOVE: MutationCommand(kind=MOVE, file_name="Old/A.md", dest="B.md"), "folder_rename": MutationCommand(kind="folder_rename", name="Old", dest="New")}[kind]
    with pytest.raises(GitFailure): service.apply(command, Origin.library(), "failed")
    assert {p.relative_to(notes.root).as_posix(): p.read_bytes() for p in notes.root.rglob("*.md")} == before
    assert notes.list_folders() == folders


def test_writing_ledger_retry_does_not_append_twice(env, monkeypatch):
    service, notes, versions, gate, factory = env
    service.apply(MutationCommand(kind=CREATE, file_name="A.md"), Origin.library(), "base")
    publish = service._ledger_status
    def fail(operation_id, status, *args, **kwargs):
        if status == "applied": raise RuntimeError("database unavailable")
        return publish(operation_id, status, *args, **kwargs)
    monkeypatch.setattr(service, "_ledger_status", fail)
    cmd = MutationCommand(kind=WRITE, file_name="A.md", content="once", append=True)
    with pytest.raises(RuntimeError): service.apply(cmd, Origin.library(), "append")
    monkeypatch.setattr(service, "_ledger_status", publish)
    service.apply(cmd, Origin.library(), "append")
    assert notes.read("A.md").count("once") == 1

def test_empty_folder_changes_have_distinct_versions(env):
    service, notes, versions, gate, factory = env
    base = versions.init()
    notes.create_folder('Empty')
    created = versions.snapshot(base, 'folder-added')
    assert not created.reused
    assert versions.folders(created.commit) == ['Empty']
    notes.rename_folder('Empty', 'Renamed')
    moved = versions.snapshot(created.commit, 'folder-moved')
    assert versions.folders(moved.commit) == ['Renamed']
