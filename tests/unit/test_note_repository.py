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


def test_rejects_nested_path(repo: FileNoteRepository):
    with pytest.raises(NotePathError):
        repo.read("sub/x.md")


def test_list_notes(repo: FileNoteRepository):
    repo.create("a.md", "A")
    repo.create("b.md", "B")
    assert repo.list_notes() == ["a.md", "b.md"]
