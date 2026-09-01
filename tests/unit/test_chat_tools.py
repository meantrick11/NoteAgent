from pathlib import Path

from noteagent.chat.drafts import DraftStore, current_thread_id
from noteagent.chat.tools import build_chat_tools
from noteagent.notes.repository import FileNoteRepository
from noteagent.retrieval.models import SearchHit


class FakeRetrieval:
    def search(self, query: str, top_k: int = 3):
        return [
            SearchHit(content=f"hit:{query}", distance=0.1, metadata={"file_name": "A.md"}),
        ]


def _tool_map(repo: FileNoteRepository, drafts: DraftStore | None = None) -> dict:
    tools = build_chat_tools(repo, FakeRetrieval(), drafts or DraftStore())
    return {tool.name: tool for tool in tools}


def test_agent_tools_do_not_write_files(tmp_path: Path):
    names = _tool_map(FileNoteRepository(tmp_path)).keys()
    assert "write_to_file" not in names
    assert "create_file" not in names
    assert "propose_note" in names


def test_search_tool_returns_fragments(tmp_path: Path):
    repo = FileNoteRepository(tmp_path)
    tools = _tool_map(repo)
    result = tools["search_relative_from_chromadb"].invoke({"query": "transformer"})
    assert result == {"fragments": ["hit:transformer"], "count": 1}


def test_tools_do_not_escape_notes(tmp_path: Path):
    repo = FileNoteRepository(tmp_path)
    tools = _tool_map(repo)
    result = tools["read_file"].invoke({"file_name": "../secret.md"})
    assert "error" in result


def _propose(tools, **kwargs):
    token = current_thread_id.set("t1")
    try:
        return tools["propose_note"].invoke(kwargs)
    finally:
        current_thread_id.reset(token)


def test_propose_append_requires_existing_file(tmp_path: Path):
    repo = FileNoteRepository(tmp_path)
    drafts = DraftStore()
    tools = _tool_map(repo, drafts)
    result = _propose(tools, action="append", file_name="Go.md", content="## 控制流\n\n- for 循环\n\n")
    assert "error" in result
    assert drafts.get("t1") is None


def test_propose_create_rejects_existing_file(tmp_path: Path):
    repo = FileNoteRepository(tmp_path)
    repo.create("Go.md", "Go")
    drafts = DraftStore()
    tools = _tool_map(repo, drafts)
    result = _propose(tools, action="create", file_name="Go.md", content="## 控制流\n\n- for 循环\n\n")
    assert "error" in result
    assert drafts.get("t1") is None


def test_propose_append_does_not_write(tmp_path: Path):
    repo = FileNoteRepository(tmp_path)
    repo.create("Backtracking.md", "Backtracking")
    before = repo.read("Backtracking.md")
    drafts = DraftStore()
    tools = _tool_map(repo, drafts)
    result = _propose(
        tools,
        action="append",
        file_name="Backtracking.md",
        content="## 切割问题\n\n- 复原 IP\n\n",
        similar="Backtracking.md",
    )
    assert result["status"] == "pending_review"
    assert repo.read("Backtracking.md") == before
    pending = drafts.get("t1")
    assert pending is not None
    assert pending.action == "append"


def test_propose_replace_requires_existing_file(tmp_path: Path):
    drafts = DraftStore()
    tools = _tool_map(FileNoteRepository(tmp_path), drafts)
    result = _propose(tools, action="replace", file_name="Go.md", content="# Go\n\n新正文\n")
    assert "error" in result
    assert drafts.get("t1") is None


def test_propose_delete_requires_existing_file(tmp_path: Path):
    drafts = DraftStore()
    tools = _tool_map(FileNoteRepository(tmp_path), drafts)
    result = _propose(tools, action="delete", file_name="Go.md")
    assert "error" in result
    assert drafts.get("t1") is None


def test_propose_replace_does_not_write(tmp_path: Path):
    repo = FileNoteRepository(tmp_path)
    repo.create("Go.md", "Go")
    repo.write("Go.md", "## 旧\n\n", append=True)
    before = repo.read("Go.md")
    drafts = DraftStore()
    tools = _tool_map(repo, drafts)
    result = _propose(tools, action="replace", file_name="Go.md", content="# Go\n\n## 新\n\n")
    assert result["status"] == "pending_review"
    assert repo.read("Go.md") == before
    assert drafts.get("t1").action == "replace"


def test_propose_delete_does_not_write(tmp_path: Path):
    repo = FileNoteRepository(tmp_path)
    repo.create("Go.md", "Go")
    drafts = DraftStore()
    tools = _tool_map(repo, drafts)
    result = _propose(tools, action="delete", file_name="Go.md")
    assert result["status"] == "pending_review"
    assert repo.exists("Go.md")
    assert drafts.get("t1").action == "delete"


def test_propose_note_uses_input_schema(tmp_path: Path):
    tools = _tool_map(FileNoteRepository(tmp_path))
    schema = tools["propose_note"].args_schema
    assert schema is not None
    field = schema.model_fields["content"]
    assert "禁止自拟" in (field.description or "")
    assert "围栏" in (field.description or "")
