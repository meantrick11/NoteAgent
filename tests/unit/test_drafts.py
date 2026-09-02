from pathlib import Path

from noteagent.chat.drafts import DraftStore, NoteDraft, commit_review
from noteagent.notes.repository import FileNoteRepository


class FakeRetrieval:
    """Records index/delete calls without Chroma."""

    def __init__(self):
        self.indexed: list[str] = []
        self.deleted: list[str] = []

    def index_note(self, file_name: str) -> int:
        self.indexed.append(file_name)
        return 1

    def delete_note(self, file_name: str) -> None:
        self.deleted.append(file_name)


class BoomRetrieval(FakeRetrieval):
    def index_note(self, file_name: str) -> int:
        raise RuntimeError("embed failed")


def _store_with(draft: NoteDraft) -> DraftStore:
    store = DraftStore()
    store.put("t1", draft)
    return store


def test_approve_appends_existing_file(tmp_path: Path):
    notes = FileNoteRepository(tmp_path)
    notes.create("Backtracking.md", "Backtracking")
    store = _store_with(NoteDraft(
        action="append",
        file_name="Backtracking.md",
        content="## 切割问题\n\n- 复原 IP\n\n",
    ))
    result = commit_review(notes, store, "t1", "approve")
    assert result == {
        "status": "written",
        "action": "append",
        "file_name": "Backtracking.md",
    }
    assert "## 切割问题" in notes.read("Backtracking.md")
    assert store.get("t1") is None


def test_approve_creates_new_file(tmp_path: Path):
    notes = FileNoteRepository(tmp_path)
    store = _store_with(NoteDraft(
        action="create",
        file_name="Go.md",
        content="## 控制流\n\n- 只有 for\n\n",
    ))
    result = commit_review(notes, store, "t1", "approve")
    assert result["status"] == "written"
    text = notes.read("Go.md")
    assert text.startswith("# Go")
    assert "## 控制流" in text


def test_override_appends_to_other_file(tmp_path: Path):
    notes = FileNoteRepository(tmp_path)
    notes.create("A.md", "A")
    notes.create("B.md", "B")
    store = _store_with(NoteDraft(
        action="create",
        file_name="C.md",
        content="## 要点\n\n- x\n\n",
    ))
    result = commit_review(
        notes,
        store,
        "t1",
        "override",
        write_action="append",
        file_name="B.md",
    )
    assert result["file_name"] == "B.md"
    assert "## 要点" in notes.read("B.md")
    assert not (tmp_path / "C.md").exists()


def test_reject_does_not_write(tmp_path: Path):
    notes = FileNoteRepository(tmp_path)
    store = _store_with(NoteDraft(
        action="create",
        file_name="Go.md",
        content="## 控制流\n\n- for\n\n",
    ))
    result = commit_review(notes, store, "t1", "reject")
    assert result == {"status": "rejected"}
    assert list(tmp_path.iterdir()) == []


def test_approve_replace_overwrites_file(tmp_path: Path):
    notes = FileNoteRepository(tmp_path)
    notes.create("Backtracking.md", "Backtracking")
    notes.write("Backtracking.md", "## 旧段\n\n- 过时\n\n", append=True)
    store = _store_with(NoteDraft(
        action="replace",
        file_name="Backtracking.md",
        content="# Backtracking\n\n## 新段\n\n更正后的正文。\n",
    ))
    result = commit_review(notes, store, "t1", "approve")
    assert result["status"] == "written"
    assert result["action"] == "replace"
    text = notes.read("Backtracking.md")
    assert "## 旧段" not in text
    assert "## 新段" in text
    assert store.get("t1") is None


def test_approve_delete_removes_file(tmp_path: Path):
    notes = FileNoteRepository(tmp_path)
    notes.create("Go.md", "Go")
    store = _store_with(NoteDraft(
        action="delete",
        file_name="Go.md",
        content="",
    ))
    result = commit_review(notes, store, "t1", "approve")
    assert result == {
        "status": "written",
        "action": "delete",
        "file_name": "Go.md",
    }
    assert notes.list_notes() == []
    assert store.get("t1") is None


def test_reject_delete_keeps_file(tmp_path: Path):
    notes = FileNoteRepository(tmp_path)
    notes.create("Go.md", "Go")
    store = _store_with(NoteDraft(
        action="delete",
        file_name="Go.md",
        content="",
    ))
    result = commit_review(notes, store, "t1", "reject")
    assert result == {"status": "rejected"}
    assert notes.exists("Go.md")


def test_approve_without_pending_errors(tmp_path: Path):
    result = commit_review(FileNoteRepository(tmp_path), DraftStore(), "t1", "approve")
    assert result == {"error": "no pending draft"}


def test_approve_create_indexes_file(tmp_path: Path):
    notes = FileNoteRepository(tmp_path)
    retrieval = FakeRetrieval()
    store = _store_with(NoteDraft(
        action="create",
        file_name="Go.md",
        content="## 控制流\n\n- 只有 for\n\n",
    ))
    result = commit_review(notes, store, "t1", "approve", retrieval=retrieval)
    assert result["status"] == "written"
    assert retrieval.indexed == ["Go.md"]
    assert retrieval.deleted == []


def test_approve_delete_drops_vectors(tmp_path: Path):
    notes = FileNoteRepository(tmp_path)
    notes.create("Go.md", "Go")
    retrieval = FakeRetrieval()
    store = _store_with(NoteDraft(
        action="delete",
        file_name="Go.md",
        content="",
    ))
    result = commit_review(notes, store, "t1", "approve", retrieval=retrieval)
    assert result["status"] == "written"
    assert retrieval.deleted == ["Go.md"]
    assert retrieval.indexed == []


def test_reject_does_not_index(tmp_path: Path):
    retrieval = FakeRetrieval()
    store = _store_with(NoteDraft(
        action="create",
        file_name="Go.md",
        content="## 控制流\n\n- for\n\n",
    ))
    commit_review(
        FileNoteRepository(tmp_path), store, "t1", "reject", retrieval=retrieval,
    )
    assert retrieval.indexed == []
    assert retrieval.deleted == []


def test_index_failure_keeps_written_file(tmp_path: Path):
    notes = FileNoteRepository(tmp_path)
    store = _store_with(NoteDraft(
        action="create",
        file_name="Go.md",
        content="## 控制流\n\n- for\n\n",
    ))
    result = commit_review(
        notes, store, "t1", "approve", retrieval=BoomRetrieval(),
    )
    assert result["status"] == "written"
    assert notes.exists("Go.md")
