"""Shadow Git note versions: byte fidelity, idempotency and isolation.

The version store must round-trip raw bytes (CRLF, Chinese, empty files), represent
empty folders through its manifest, reuse a commit when nothing changed, and never
touch the notes tree or the production git repository.
"""

from __future__ import annotations

import subprocess

import pytest

from NoteAgent.BusinessModules.NoteStorage.MarkdownRepository import FileNoteRepository
from NoteAgent.BusinessModules.NoteStorage.NoteVersions import NoteVersionError, NoteVersionStore


@pytest.fixture
def store(tmp_path):
    notes = FileNoteRepository(tmp_path / "notes")
    repo = tmp_path / "history"
    return NoteVersionStore(repo, notes.root), notes, tmp_path


def test_init_and_read_blob_round_trip_bytes(store):
    versions, notes, _ = store
    notes.create("A.md", "A")
    notes.write("A.md", "第一行\r\n第二行\r\n", append=False)

    commit = versions.init()
    assert len(commit) == 40
    # Byte-for-byte, including CRLF and the platform's newline translation on write.
    assert versions.read_blob(commit, "A.md") == (notes.root / "A.md").read_bytes()
    assert versions.read_blob(commit, "missing.md") is None


def test_empty_file_and_empty_folder_are_tracked(store):
    versions, notes, _ = store
    notes.create("E.md", "E")  # body written below as empty
    (notes.root / "E.md").write_bytes(b"")
    (notes.root / "空旷").mkdir()

    commit = versions.init()
    assert versions.read_blob(commit, "E.md") == b""
    assert "空旷" in versions.folders(commit)


def test_move_and_delete_record_changed_paths(store):
    versions, notes, _ = store
    notes.create("A.md", "A")
    notes.write("A.md", "body\n", append=False)
    first = versions.init()

    notes.move("A.md", "B.md")
    moved = versions.snapshot(first, operation_id="op-move")
    assert moved.commit != first
    assert "B.md" in moved.changed_paths and "A.md" in moved.changed_paths
    assert versions.read_blob(moved.commit, "A.md") is None
    assert versions.read_blob(moved.commit, "B.md") == (notes.root / "B.md").read_bytes()

    notes.delete("B.md")
    deleted = versions.snapshot(moved.commit, operation_id="op-delete")
    assert "B.md" in deleted.changed_paths
    assert versions.read_blob(deleted.commit, "B.md") is None


def test_no_change_reuses_commit_and_same_operation_retries(store):
    versions, notes, _ = store
    notes.create("A.md", "A")
    notes.write("A.md", "x\n", append=False)
    first = versions.init()

    again = versions.snapshot(first, operation_id="op-1")
    assert again.reused is True
    assert again.commit == first
    assert again.changed_paths == []

    # Same operation id twice keeps pointing at the same commit.
    retried = versions.snapshot(first, operation_id="op-1")
    assert retried.commit == first
    assert versions.resolve_ref("op-1") == first


def test_repository_reopen_can_still_read_blobs(store):
    versions, notes, tmp_path = store
    notes.create("A.md", "A")
    notes.write("A.md", "reopen me\n", append=False)
    commit = versions.init()

    reopened = NoteVersionStore(tmp_path / "history", notes.root)
    assert reopened.read_blob(commit, "A.md") == (notes.root / "A.md").read_bytes()
    assert reopened.resolve_ref("init") == commit


def test_notes_tree_and_code_repo_are_untouched(store):
    versions, notes, tmp_path = store
    notes.create("A.md", "A")
    versions.init()

    # No .git is written into the notes directory.
    assert not (notes.root / ".git").exists()

    # A code repository next door keeps its HEAD and index exactly as they were.
    code = tmp_path / "code"
    code.mkdir()
    subprocess.run(["git", "init", "-q", str(code)], check=True, shell=False)
    (code / "f.txt").write_text("keep", encoding="utf-8")
    head_before = subprocess.run(
        ["git", "-C", str(code), "rev-parse", "--verify", "-q", "HEAD"],
        capture_output=True, shell=False,
    ).returncode
    notes.write("A.md", "changed\n", append=False)
    versions.snapshot(versions.resolve_ref("init"), operation_id="op-2")
    head_after = subprocess.run(
        ["git", "-C", str(code), "rev-parse", "--verify", "-q", "HEAD"],
        capture_output=True, shell=False,
    ).returncode
    assert head_before == head_after  # neither repo has a commit; still untouched
    assert subprocess.run(
        ["git", "-C", str(code), "status", "--porcelain"],
        capture_output=True, text=True, shell=False,
    ).stdout.strip() == "?? f.txt"


def test_unsafe_paths_and_commits_are_rejected(store):
    versions, notes, _ = store
    notes.create("A.md", "A")
    commit = versions.init()

    with pytest.raises(NoteVersionError):
        versions.read_blob(commit, "../escape.md")
    with pytest.raises(NoteVersionError):
        versions.read_blob(commit, "/abs.md")
    with pytest.raises(NoteVersionError):
        versions.read_blob("--help", "A.md")
    with pytest.raises(NoteVersionError):
        versions.snapshot("not-a-commit", operation_id="op")


def test_symlink_out_of_tree_is_not_tracked(tmp_path):
    notes = FileNoteRepository(tmp_path / "notes")
    outside = tmp_path / "outside.md"
    outside.write_text("secret", encoding="utf-8")
    link = notes.root / "link.md"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not supported on this platform")

    versions = NoteVersionStore(tmp_path / "history", notes.root)
    commit = versions.init()
    assert versions.read_blob(commit, "link.md") is None
