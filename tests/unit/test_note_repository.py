from pathlib import Path

import pytest

from noteagent.notes.repository import FileNoteRepository, NotePathError


@pytest.fixture
def repo(tmp_path: Path) -> FileNoteRepository:
    return FileNoteRepository(tmp_path)


def test_create_read_append_overwrite(repo: FileNoteRepository):
    created = repo.create("Agent", "Agent")
    assert created == "Agent.md"
    assert repo.read("Agent.md") == "# Agent\n\n"

    repo.write("Agent.md", "## First\n\n", append=True)
    assert "## First" in repo.read("Agent.md")

    repo.write("Agent.md", "# Only\n", append=False)
    assert repo.read("Agent.md") == "# Only\n"


def test_create_existing_raises(repo: FileNoteRepository):
    repo.create("LLM.md", "LLM")
    with pytest.raises(FileExistsError):
        repo.create("LLM.md", "LLM")


def test_write_missing_file_raises(repo: FileNoteRepository):
    with pytest.raises(FileNotFoundError):
        repo.write("missing.md", "x")


def test_rejects_parent_escape(repo: FileNoteRepository):
    with pytest.raises(NotePathError):
        repo.read("../secret.md")


def test_rejects_absolute_path(repo: FileNoteRepository, tmp_path: Path):
    with pytest.raises(NotePathError):
        repo.read(str(tmp_path / "x.md"))


def test_rejects_two_level_path(repo: FileNoteRepository):
    with pytest.raises(NotePathError):
        repo.read("a/b/x.md")


def test_one_level_create_read_list(repo: FileNoteRepository):
    created = repo.create("Python/GIL.md", "GIL")
    assert created == "Python/GIL.md"
    assert repo.read("Python/GIL.md") == "# GIL\n\n"
    assert repo.list_notes() == ["Python/GIL.md"]
    assert repo.list_folders() == ["Python"]
    assert repo.exists("Python/GIL.md")


def test_create_folder_and_move(repo: FileNoteRepository):
    repo.create("Go.md", "Go")
    repo.create_folder("Lang")
    moved = repo.move("Go.md", "Lang/Go.md")
    assert moved == "Lang/Go.md"
    assert not repo.exists("Go.md")
    assert repo.read("Lang/Go.md").startswith("# Go")


def test_create_folder_rejects_nested(repo: FileNoteRepository):
    with pytest.raises(NotePathError):
        repo.create_folder("a/b")


def test_move_missing_raises(repo: FileNoteRepository):
    with pytest.raises(FileNotFoundError):
        repo.move("missing.md", "Lang/missing.md")


def test_delete_existing_file(repo: FileNoteRepository):
    repo.create("Go.md", "Go")
    repo.delete("Go.md")
    assert repo.list_notes() == []


def test_delete_missing_raises(repo: FileNoteRepository):
    with pytest.raises(FileNotFoundError):
        repo.delete("missing.md")


def test_delete_rejects_parent_escape(repo: FileNoteRepository):
    with pytest.raises(NotePathError):
        repo.delete("../secret.md")


def test_list_notes(repo: FileNoteRepository):
    repo.create("a.md", "A")
    repo.create("b.md", "B")
    assert repo.list_notes() == ["a.md", "b.md"]


def test_rename_folder_moves_notes(repo: FileNoteRepository):
    repo.create("Lang/Go.md", "Go")
    repo.create("Lang/Python.md", "Python")
    old, new, pairs = repo.rename_folder("Lang", "Runtime")
    assert old == "Lang"
    assert new == "Runtime"
    assert pairs == [("Lang/Go.md", "Runtime/Go.md"), ("Lang/Python.md", "Runtime/Python.md")]
    assert repo.list_folders() == ["Runtime"]
    assert repo.list_notes() == ["Runtime/Go.md", "Runtime/Python.md"]
    assert repo.read("Runtime/Go.md").startswith("# Go")


def test_rename_folder_rejects_existing(repo: FileNoteRepository):
    repo.create_folder("A")
    repo.create_folder("B")
    with pytest.raises(FileExistsError):
        repo.rename_folder("A", "B")


def test_rename_folder_rejects_nested(repo: FileNoteRepository):
    repo.create_folder("A")
    with pytest.raises(NotePathError):
        repo.rename_folder("A", "B/C")


def test_delete_folder_removes_notes(repo: FileNoteRepository):
    repo.create("Lang/Go.md", "Go")
    repo.create("Root.md", "Root")
    deleted = repo.delete_folder("Lang")
    assert deleted == ["Lang/Go.md"]
    assert repo.list_folders() == []
    assert repo.list_notes() == ["Root.md"]


def test_delete_folder_missing_raises(repo: FileNoteRepository):
    with pytest.raises(FileNotFoundError):
        repo.delete_folder("Missing")
