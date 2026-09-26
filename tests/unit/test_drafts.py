from pathlib import Path

import pytest

from noteagent.chat.drafts import DraftStore, NoteDraft, commit_review
from noteagent.chat.history import ConversationStore
from noteagent.db import Base, create_engine_from_url, create_session_factory
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


def _raiser(error: Exception):
    """Build a stand-in for a repository method that fails before touching disk."""
    def fail(*args, **kwargs):
        raise error
    return fail


def _store_with(draft: NoteDraft) -> tuple[DraftStore, str]:
    engine = create_engine_from_url("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    history = ConversationStore(create_session_factory(engine))
    conv = history.create("t")
    store = DraftStore(history)
    store.put(conv.id, draft)
    return store, conv.id


def test_approve_appends_existing_file(tmp_path: Path):
    notes = FileNoteRepository(tmp_path)
    notes.create("Backtracking.md", "Backtracking")
    store, tid = _store_with(NoteDraft(
        action="append",
        file_name="Backtracking.md",
        content="## 切割问题\n\n- 复原 IP\n\n",
    ))
    result = commit_review(notes, store, tid, "approve")
    assert result == {
        "status": "written",
        "action": "append",
        "file_name": "Backtracking.md",
    }
    assert "## 切割问题" in notes.read("Backtracking.md")
    assert store.get(tid) is None


def test_approve_creates_new_file(tmp_path: Path):
    notes = FileNoteRepository(tmp_path)
    store, tid = _store_with(NoteDraft(
        action="create",
        file_name="Go.md",
        content="## 控制流\n\n- 只有 for\n\n",
    ))
    result = commit_review(notes, store, tid, "approve")
    assert result["status"] == "written"
    text = notes.read("Go.md")
    assert text.startswith("# Go")
    assert "## 控制流" in text


def test_approve_creates_file_in_folder_uses_stem_title(tmp_path: Path):
    notes = FileNoteRepository(tmp_path)
    notes.create_folder("Python")
    store, tid = _store_with(NoteDraft(
        action="create",
        file_name="Python/GIL.md",
        content="## 锁\n\n解释器锁。\n\n",
    ))
    result = commit_review(notes, store, tid, "approve")
    assert result == {
        "status": "written",
        "action": "create",
        "file_name": "Python/GIL.md",
    }
    text = notes.read("Python/GIL.md")
    assert text.startswith("# GIL")
    assert "## 锁" in text


def test_override_appends_to_other_file(tmp_path: Path):
    notes = FileNoteRepository(tmp_path)
    notes.create("A.md", "A")
    notes.create("B.md", "B")
    store, tid = _store_with(NoteDraft(
        action="create",
        file_name="C.md",
        content="## 要点\n\n- x\n\n",
    ))
    result = commit_review(
        notes,
        store,
        tid,
        "override",
        write_action="append",
        file_name="B.md",
    )
    assert result["file_name"] == "B.md"
    assert "## 要点" in notes.read("B.md")
    assert not (tmp_path / "C.md").exists()


def test_reject_does_not_write(tmp_path: Path):
    notes = FileNoteRepository(tmp_path)
    store, tid = _store_with(NoteDraft(
        action="create",
        file_name="Go.md",
        content="## 控制流\n\n- for\n\n",
    ))
    result = commit_review(notes, store, tid, "reject")
    assert result == {"status": "rejected"}
    assert list(tmp_path.iterdir()) == []


def test_approve_replace_overwrites_file(tmp_path: Path):
    notes = FileNoteRepository(tmp_path)
    notes.create("Backtracking.md", "Backtracking")
    notes.write("Backtracking.md", "## 旧段\n\n- 过时\n\n", append=True)
    store, tid = _store_with(NoteDraft(
        action="replace",
        file_name="Backtracking.md",
        content="# Backtracking\n\n## 新段\n\n更正后的正文。\n",
    ))
    result = commit_review(notes, store, tid, "approve")
    assert result["status"] == "written"
    assert result["action"] == "replace"
    text = notes.read("Backtracking.md")
    assert "## 旧段" not in text
    assert "## 新段" in text
    assert store.get(tid) is None


def test_approve_delete_removes_file(tmp_path: Path):
    notes = FileNoteRepository(tmp_path)
    notes.create("Go.md", "Go")
    store, tid = _store_with(NoteDraft(
        action="delete",
        file_name="Go.md",
        content="",
    ))
    result = commit_review(notes, store, tid, "approve")
    assert result == {
        "status": "written",
        "action": "delete",
        "file_name": "Go.md",
    }
    assert notes.list_notes() == []
    assert store.get(tid) is None


def test_reject_delete_keeps_file(tmp_path: Path):
    notes = FileNoteRepository(tmp_path)
    notes.create("Go.md", "Go")
    store, tid = _store_with(NoteDraft(
        action="delete",
        file_name="Go.md",
        content="",
    ))
    result = commit_review(notes, store, tid, "reject")
    assert result == {"status": "rejected"}
    assert notes.exists("Go.md")


def test_approve_without_pending_errors(tmp_path: Path):
    engine = create_engine_from_url("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    history = ConversationStore(create_session_factory(engine))
    conv = history.create("t")
    result = commit_review(
        FileNoteRepository(tmp_path), DraftStore(history), conv.id, "approve",
    )
    assert result == {"error": "no pending draft"}


def test_approve_create_indexes_file(tmp_path: Path):
    notes = FileNoteRepository(tmp_path)
    retrieval = FakeRetrieval()
    store, tid = _store_with(NoteDraft(
        action="create",
        file_name="Go.md",
        content="## 控制流\n\n- 只有 for\n\n",
    ))
    result = commit_review(notes, store, tid, "approve", retrieval=retrieval)
    assert result["status"] == "written"
    assert retrieval.indexed == ["Go.md"]
    assert retrieval.deleted == []


def test_approve_delete_drops_vectors(tmp_path: Path):
    notes = FileNoteRepository(tmp_path)
    notes.create("Go.md", "Go")
    retrieval = FakeRetrieval()
    store, tid = _store_with(NoteDraft(
        action="delete",
        file_name="Go.md",
        content="",
    ))
    result = commit_review(notes, store, tid, "approve", retrieval=retrieval)
    assert result["status"] == "written"
    assert retrieval.deleted == ["Go.md"]
    assert retrieval.indexed == []


def test_reject_does_not_index(tmp_path: Path):
    retrieval = FakeRetrieval()
    store, tid = _store_with(NoteDraft(
        action="create",
        file_name="Go.md",
        content="## 控制流\n\n- for\n\n",
    ))
    commit_review(
        FileNoteRepository(tmp_path), store, tid, "reject", retrieval=retrieval,
    )
    assert retrieval.indexed == []
    assert retrieval.deleted == []


def test_index_failure_keeps_written_file(tmp_path: Path):
    notes = FileNoteRepository(tmp_path)
    store, tid = _store_with(NoteDraft(
        action="create",
        file_name="Go.md",
        content="## 控制流\n\n- for\n\n",
    ))
    result = commit_review(
        notes, store, tid, "approve", retrieval=BoomRetrieval(),
    )
    assert result["status"] == "written"
    assert notes.exists("Go.md")


@pytest.mark.parametrize("error", [PermissionError("denied"), OSError("disk failure")])
def test_write_error_preserves_draft_and_allows_retry(tmp_path, monkeypatch, error):
    notes = FileNoteRepository(tmp_path)
    notes.create("A.md", "A")
    before = notes.read("A.md")
    draft = NoteDraft(action="append", file_name="A.md", content="## New\n\nbody\n")
    store, tid = _store_with(draft)
    retrieval = FakeRetrieval()
    original_write = notes.write

    def fail_write(*args, **kwargs):
        raise error

    monkeypatch.setattr(notes, "write", fail_write)
    result = commit_review(notes, store, tid, "approve", retrieval=retrieval)
    assert "error" in result
    # 新包装器重新读取同一个测试数据库，不能只检查局部 draft 变量。
    assert DraftStore(store._history).get(tid).as_dict() == draft.as_dict()
    assert notes.read("A.md") == before
    assert retrieval.indexed == []
    assert retrieval.deleted == []

    monkeypatch.setattr(notes, "write", original_write)
    result = commit_review(notes, store, tid, "approve", retrieval=retrieval)
    assert result["status"] == "written"
    assert store.get(tid) is None
    assert notes.read("A.md").count("## New") == 1
    assert retrieval.indexed == ["A.md"]


def test_create_error_before_creation_preserves_draft(tmp_path, monkeypatch):
    notes = FileNoteRepository(tmp_path)
    draft = NoteDraft(action="create", file_name="Go.md", content="## 控制流\n\n- for\n\n")
    store, tid = _store_with(draft)
    retrieval = FakeRetrieval()
    original_create = notes.create

    monkeypatch.setattr(notes, "create", _raiser(PermissionError("denied")))
    result = commit_review(notes, store, tid, "approve", retrieval=retrieval)
    assert result["error"] == "denied"
    assert DraftStore(store._history).get(tid).as_dict() == draft.as_dict()
    assert not (tmp_path / "Go.md").exists()
    assert retrieval.indexed == []
    assert retrieval.deleted == []

    monkeypatch.setattr(notes, "create", original_create)
    result = commit_review(notes, store, tid, "approve", retrieval=retrieval)
    assert result["status"] == "written"
    assert notes.read("Go.md").startswith("# Go")
    assert retrieval.indexed == ["Go.md"]


def test_replace_error_keeps_original_text_and_draft(tmp_path, monkeypatch):
    notes = FileNoteRepository(tmp_path)
    notes.create("A.md", "A")
    notes.write("A.md", "## 旧段\n\n- 过时\n\n", append=True)
    before = notes.read("A.md")
    draft = NoteDraft(
        action="replace",
        file_name="A.md",
        content="# A\n\n## 新段\n\n更正后的正文。\n",
    )
    store, tid = _store_with(draft)
    original_write = notes.write

    monkeypatch.setattr(notes, "write", _raiser(OSError("disk failure")))
    result = commit_review(notes, store, tid, "approve")
    assert "error" in result
    assert notes.read("A.md") == before
    assert DraftStore(store._history).get(tid).as_dict() == draft.as_dict()

    monkeypatch.setattr(notes, "write", original_write)
    result = commit_review(notes, store, tid, "approve")
    assert result["status"] == "written"
    assert notes.read("A.md") == draft.content


def test_delete_error_keeps_file_and_draft(tmp_path, monkeypatch):
    notes = FileNoteRepository(tmp_path)
    notes.create("Go.md", "Go")
    draft = NoteDraft(action="delete", file_name="Go.md", content="")
    store, tid = _store_with(draft)
    retrieval = FakeRetrieval()
    original_delete = notes.delete

    monkeypatch.setattr(notes, "delete", _raiser(PermissionError("denied")))
    result = commit_review(notes, store, tid, "approve", retrieval=retrieval)
    assert result["error"] == "denied"
    assert notes.exists("Go.md")
    assert DraftStore(store._history).get(tid).as_dict() == draft.as_dict()
    assert retrieval.deleted == []
    assert retrieval.indexed == []

    monkeypatch.setattr(notes, "delete", original_delete)
    result = commit_review(notes, store, tid, "approve", retrieval=retrieval)
    assert result["status"] == "written"
    assert not notes.exists("Go.md")
    assert retrieval.deleted == ["Go.md"]


def test_override_write_error_keeps_original_proposal(tmp_path, monkeypatch):
    notes = FileNoteRepository(tmp_path)
    notes.create("A.md", "A")
    notes.create("B.md", "B")
    before_b = notes.read("B.md")
    draft = NoteDraft(
        action="create",
        file_name="C.md",
        content="## 要点\n\n- x\n\n",
        reason="归到 B",
        similar=["B.md"],
    )
    store, tid = _store_with(draft)
    original_write = notes.write

    monkeypatch.setattr(notes, "write", _raiser(OSError("disk failure")))
    result = commit_review(
        notes, store, tid, "override", write_action="append", file_name="B.md",
    )
    assert "error" in result
    assert DraftStore(store._history).get(tid).as_dict() == draft.as_dict()
    assert notes.read("B.md") == before_b
    assert not (tmp_path / "C.md").exists()

    monkeypatch.setattr(notes, "write", original_write)
    result = commit_review(
        notes, store, tid, "override", write_action="append", file_name="B.md",
    )
    assert result["status"] == "written"
    assert result["file_name"] == "B.md"
    assert "## 要点" in notes.read("B.md")


def test_create_partial_write_keeps_draft_but_leaves_title_file(tmp_path, monkeypatch):
    notes = FileNoteRepository(tmp_path)
    draft = NoteDraft(action="create", file_name="Go.md", content="## 控制流\n\n- for\n\n")
    store, tid = _store_with(draft)
    retrieval = FakeRetrieval()
    original_write = notes.write

    monkeypatch.setattr(notes, "write", _raiser(OSError("disk failure")))
    result = commit_review(notes, store, tid, "approve", retrieval=retrieval)
    assert "error" in result
    # 标题已落盘、正文未写入：这是部分写入，不是无损失败。
    assert (tmp_path / "Go.md").read_text(encoding="utf-8") == "# Go\n\n"
    assert DraftStore(store._history).get(tid).as_dict() == draft.as_dict()
    assert retrieval.indexed == []

    # 同一草稿再次 create 会撞上残留标题文件（FileExistsError），必须人工核对文件后处理。
    monkeypatch.setattr(notes, "write", original_write)
    result = commit_review(notes, store, tid, "approve", retrieval=retrieval)
    assert "error" in result
    assert (tmp_path / "Go.md").read_text(encoding="utf-8") == "# Go\n\n"
    assert DraftStore(store._history).get(tid).as_dict() == draft.as_dict()
