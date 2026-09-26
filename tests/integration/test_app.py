import json
from pathlib import Path

from fastapi.testclient import TestClient

from noteagent.bootstrap.app import AppContainer, create_app
from noteagent.bootstrap.settings import Settings
from noteagent.chat.drafts import DraftStore, NoteDraft, commit_review
from noteagent.chat.history import ConversationStore, start_turn
from noteagent.db import Base, create_engine_from_url, create_session_factory
from noteagent.model_management.service import ModelRuntimeService
from noteagent.model_management.store import ModelSettingsStore
from noteagent.notes.repository import FileNoteRepository
from noteagent.web import read_home_html


class FakeAgent:
    async def stream(self, question: str, thread_id: str, turn_id: str | None = None):
        yield {"event": "token", "data": f"echo:{question}"}
        yield {"event": "assistant_final", "data": f"echo:{question}"}

    def review(self, thread_id: str, action: str, write_action=None, file_name=None):
        return {"status": "rejected"} if action == "reject" else {"status": "written", "file_name": "Go.md"}


class StubRetrieval:
    """Placeholder index for tests that never search it."""

    def config_fingerprint(self) -> str:
        return "stub-config"

    def verify_index(self) -> bool:
        return True

    def point_count(self) -> int:
        return 0


class StubAssembler:
    """Hands back the agent a test injected; never builds a real model."""

    def __init__(self, agent, retrieval=None):
        self._agent = agent
        self._retrieval = retrieval if retrieval is not None else StubRetrieval()

    def build_chat_model(self, profile):
        raise AssertionError("integration tests must not build a real chat model")

    def index_fingerprint(self, *, model_id, resolved_revision):
        return f"stub:{model_id}:{resolved_revision or ''}"

    def build_retrieval(
        self, *, model_id, resolved_revision, collection, local_files_only, create_if_missing
    ):
        return self._retrieval

    def build_agent(self, *, profile, retrieval):
        return self._agent


def _sqlite_history():
    engine = create_engine_from_url("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine, ConversationStore(create_session_factory(engine))


def _container(
    settings: Settings,
    notes: FileNoteRepository,
    engine,
    history: ConversationStore,
    agent,
    retrieval=None,
) -> AppContainer:
    """Build a container whose runtime hands out the injected fakes."""
    runtime = ModelRuntimeService(
        settings=settings,
        store=ModelSettingsStore(settings.model_settings_dir),
        notes=notes,
        assembler=StubAssembler(agent, retrieval),
    )
    runtime.initialize()
    return AppContainer(
        settings=settings,
        notes=notes,
        engine=engine,
        history=history,
        model_runtime=runtime,
    )


def _client(tmp_path: Path) -> tuple[TestClient, ConversationStore]:
    settings = Settings(
        notes_dir=tmp_path,
        chroma_dir=tmp_path / "chroma",
        model_settings_dir=tmp_path / "model_settings",
    )
    engine, history = _sqlite_history()
    container = _container(settings, FileNoteRepository(tmp_path), engine, history, FakeAgent())
    return TestClient(create_app(container)), history


class RealDraftAgent(FakeAgent):
    """Draft edits and reviews go through the real store, not a stub."""

    def __init__(self, notes: FileNoteRepository, drafts: DraftStore) -> None:
        self._notes = notes
        self._drafts = drafts

    def update_draft_content(self, thread_id: str, content: str) -> dict:
        draft = self._drafts.update_content(thread_id, content)
        if draft is None:
            return {"error": "no pending draft"}
        return {"status": "updated", "pending_draft": draft.as_dict()}

    def review(self, thread_id: str, action: str, write_action=None, file_name=None):
        return commit_review(
            self._notes, self._drafts, thread_id, action, write_action, file_name,
        )


def _draft_client(
    tmp_path: Path,
) -> tuple[TestClient, ConversationStore, FileNoteRepository, DraftStore]:
    """Client whose agent persists draft edits and approvals for real."""
    settings = Settings(
        notes_dir=tmp_path,
        chroma_dir=tmp_path / "chroma",
        model_settings_dir=tmp_path / "model_settings",
    )
    notes = FileNoteRepository(tmp_path)
    engine, history = _sqlite_history()
    drafts = DraftStore(history)
    container = _container(settings, notes, engine, history, RealDraftAgent(notes, drafts))
    return TestClient(create_app(container)), history, notes, drafts


def _parse_sse(text: str) -> list[tuple[str, str]]:
    """Parse an SSE body into a list of (event, data) pairs."""
    events = []
    event = "message"
    data = None
    for line in text.splitlines():
        if line.startswith("event: "):
            event = line[7:].strip()
        elif line.startswith("data: "):
            data = line[6:]
        elif line.strip() == "":
            if data is not None:
                events.append((event, data))
            event = "message"
            data = None
    return events


def _collect_tokens(text: str) -> str:
    """Concatenate all token event data (JSON-decoded) from an SSE body."""
    return "".join(
        json.loads(data) for event, data in _parse_sse(text) if event == "token"
    )


def test_home_serves_template(tmp_path: Path):
    client, _ = _client(tmp_path)
    response = client.get("/")
    assert response.status_code == 200
    assert "NoteAgent" in response.text
    assert "conversationList" in response.text
    assert "Documents" in response.text
    assert "btnNewNote" in response.text
    assert "citePaneSave" in response.text
    assert "citePaneText" in response.text
    assert "citePaneByConv" in response.text
    assert "localizeCitations" in response.text
    assert "移动到所选" not in response.text
    assert read_home_html() == response.text


def test_documents_route_serves_same_template(tmp_path: Path):
    client, _ = _client(tmp_path)
    response = client.get("/documents")
    assert response.status_code == 200
    assert "Documents" in response.text
    assert read_home_html() == response.text


def test_chat_and_review_routes(tmp_path: Path):
    client, history = _client(tmp_path)
    record = history.create("t")
    chat = client.post("/chat", json={"question": "你好", "thread_id": record.id})
    assert chat.status_code == 200
    assert chat.headers["content-type"].startswith("text/event-stream")
    assert "event: conversation" in chat.text
    assert "event: answer" in chat.text
    assert _collect_tokens(chat.text) == "echo:你好"

    review = client.post(
        "/chat/review",
        json={"thread_id": record.id, "action": "reject"},
    )
    assert review.status_code == 200
    assert review.json()["status"] == "rejected"


def test_chat_persists_messages(tmp_path: Path):
    client, _ = _client(tmp_path)

    chat = client.post("/chat", json={"question": "你好"})
    assert chat.status_code == 200
    events = _parse_sse(chat.text)
    conv_data = next(data for event, data in events if event == "conversation")
    conv_id = json.loads(conv_data)["id"]

    messages = client.get(f"/conversations/{conv_id}/messages").json()
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert "echo:你好" in messages[1]["content"]

    chat = client.post(
        "/chat",
        json={"question": "x", "conversation_id": "00000000-0000-0000-0000-000000000001"},
    )
    assert chat.status_code == 404

    chat = client.post("/chat", json={"question": "第二轮", "thread_id": conv_id})
    assert chat.status_code == 200
    messages = client.get(f"/conversations/{conv_id}/messages").json()
    assert len(messages) == 4


def test_messages_api_returns_citations(tmp_path: Path):
    client, history = _client(tmp_path)
    record = history.create("t")
    tid = start_turn()
    cites = [{"index": 1, "file_name": "Go.md", "chunk_index": 0, "quote": "hi"}]
    history.append_message(record.id, "user", "q", turn_id=tid)
    history.append_message(
        record.id, "assistant", "a[[cite:1]]", turn_id=tid, citations=cites,
    )
    resp = client.get(f"/conversations/{record.id}/messages")
    assert resp.status_code == 200
    body = resp.json()
    assert body[1]["citations"] == cites


def test_messages_api_hides_tool_stubs(tmp_path: Path):
    client, history = _client(tmp_path)
    record = history.create("t")
    tid = start_turn()
    history.append_message(record.id, "user", "hi", turn_id=tid)
    history.append_tool_stub(
        record.id, turn_id=tid, tool_name="read_file",
        arguments='{"file_name":"A.md"}', output="x" * 200,
        status="ok", stub_preview_tokens=2, args_preview_chars=500,
    )
    history.append_message(record.id, "assistant", "done", turn_id=tid)

    resp = client.get(f"/conversations/{record.id}/messages")
    assert resp.status_code == 200
    assert [m["role"] for m in resp.json()] == ["user", "assistant"]
    assert resp.json()[0]["tool_steps"] == []
    assert resp.json()[1]["tool_steps"][0]["name"] == "read_file"


def test_chat_persists_final_assistant_not_tool_hop_tokens(tmp_path: Path):
    class FakeToolHopAgent:
        async def stream(self, question: str, thread_id: str, turn_id: str | None = None):
            yield {"event": "token", "data": "calling-tool"}
            yield {"event": "assistant_final", "data": "done"}

        def review(self, thread_id: str, action: str, write_action=None, file_name=None):
            return {"status": "rejected"}

    settings = Settings(
        notes_dir=tmp_path,
        chroma_dir=tmp_path / "chroma",
        model_settings_dir=tmp_path / "model_settings",
    )
    engine, history = _sqlite_history()
    container = _container(
        settings, FileNoteRepository(tmp_path), engine, history, FakeToolHopAgent()
    )
    client = TestClient(create_app(container))
    chat = client.post("/chat", json={"question": "hi"})
    assert chat.status_code == 200
    events = _parse_sse(chat.text)
    conv_data = next(data for event, data in events if event == "conversation")
    conv_id = json.loads(conv_data)["id"]
    messages = client.get(f"/conversations/{conv_id}/messages").json()
    assert messages[1]["content"] == "done"
    assert _collect_tokens(chat.text) == "calling-tool"


def test_chat_sse_forwards_multiple_token_events(tmp_path: Path):
    class FakeChunkAgent:
        async def stream(self, question: str, thread_id: str, turn_id: str | None = None):
            yield {"event": "thinking", "data": "thinking"}
            yield {"event": "token", "data": "Hel"}
            yield {"event": "token", "data": "lo"}
            yield {"event": "assistant_final", "data": "Hello"}

        def review(self, thread_id: str, action: str, write_action=None, file_name=None):
            return {"status": "rejected"}

    settings = Settings(
        notes_dir=tmp_path,
        chroma_dir=tmp_path / "chroma",
        model_settings_dir=tmp_path / "model_settings",
    )
    engine, history = _sqlite_history()
    container = _container(
        settings, FileNoteRepository(tmp_path), engine, history, FakeChunkAgent()
    )
    client = TestClient(create_app(container))
    chat = client.post("/chat", json={"question": "hi"})
    tokens = [data for event, data in _parse_sse(chat.text) if event == "token"]
    assert [json.loads(t) for t in tokens] == ["Hel", "lo"]
    events = _parse_sse(chat.text)
    conv_id = json.loads(next(data for event, data in events if event == "conversation"))["id"]
    messages = client.get(f"/conversations/{conv_id}/messages").json()
    assert messages[1]["content"] == "Hello"


def test_conversations_and_messages_routes(tmp_path: Path):
    client, history = _client(tmp_path)

    resp = client.get("/conversations")
    assert resp.status_code == 200
    assert resp.json() == []

    record = history.create("t")
    history.append_message(record.id, "user", "hi", turn_id=start_turn())

    resp = client.get("/conversations")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["id"] == record.id
    assert resp.json()[0]["title"] == "t"

    resp = client.get(f"/conversations/{record.id}/messages")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["role"] == "user"
    assert resp.json()[0]["content"] == "hi"
    assert resp.json()[0]["citations"] == []

    resp = client.get("/conversations/00000000-0000-0000-0000-000000000001/messages")
    assert resp.status_code == 404


def test_rename_conversation_route(tmp_path: Path):
    client, history = _client(tmp_path)
    record = history.create("old")

    resp = client.patch(f"/conversations/{record.id}", json={"title": " 新名字 "})
    assert resp.status_code == 200
    assert resp.json()["title"] == "新名字"
    assert resp.json()["id"] == record.id

    listing = client.get("/conversations").json()
    assert listing[0]["title"] == "新名字"


def test_rename_conversation_unknown_id(tmp_path: Path):
    client, _ = _client(tmp_path)
    resp = client.patch(
        "/conversations/00000000-0000-0000-0000-000000000001",
        json={"title": "x"},
    )
    assert resp.status_code == 404


def test_rename_conversation_blank_title(tmp_path: Path):
    client, history = _client(tmp_path)
    record = history.create("old")
    resp = client.patch(f"/conversations/{record.id}", json={"title": "   "})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "title is required"


def test_rename_conversation_too_long(tmp_path: Path):
    client, history = _client(tmp_path)
    record = history.create("old")
    resp = client.patch(f"/conversations/{record.id}", json={"title": "x" * 81})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "title too long"


def test_delete_conversation_route(tmp_path: Path):
    client, history = _client(tmp_path)
    record = history.create("t")
    tid = start_turn()
    history.append_message(record.id, "user", "hi", turn_id=tid)
    history.append_message(record.id, "assistant", "hello", turn_id=tid)

    resp = client.delete(f"/conversations/{record.id}")
    assert resp.status_code == 204
    assert resp.content == b""

    assert client.get(f"/conversations/{record.id}/messages").status_code == 404
    ids = [c["id"] for c in client.get("/conversations").json()]
    assert record.id not in ids


def test_delete_conversation_unknown_id(tmp_path: Path):
    client, _ = _client(tmp_path)
    resp = client.delete("/conversations/00000000-0000-0000-0000-000000000001")
    assert resp.status_code == 404


_DRAFT_PAYLOAD = {
    "action": "create",
    "file_name": "Go.md",
    "content": "## 控制流\n\n",
    "reason": "新文件",
    "similar": [],
    "existing_files": [],
}


def test_get_conversation_includes_pending_draft(tmp_path: Path):
    client, history = _client(tmp_path)
    record = history.create("t")
    history.set_pending_draft(record.id, _DRAFT_PAYLOAD)

    resp = client.get(f"/conversations/{record.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == record.id
    assert body["title"] == "t"
    assert body["pending_draft"]["file_name"] == "Go.md"

    messages = client.get(f"/conversations/{record.id}/messages").json()
    assert messages == []


def test_get_conversation_unknown_id(tmp_path: Path):
    client, _ = _client(tmp_path)
    resp = client.get("/conversations/00000000-0000-0000-0000-000000000001")
    assert resp.status_code == 404


def test_review_clears_pending_draft(tmp_path: Path):
    from noteagent.chat.drafts import DraftStore, NoteDraft, commit_review

    notes = FileNoteRepository(tmp_path)
    engine, history = _sqlite_history()
    drafts = DraftStore(history)

    class ReviewAgent(FakeAgent):
        def review(self, thread_id: str, action: str, write_action=None, file_name=None):
            return commit_review(
                notes, drafts, thread_id, action, write_action, file_name,
            )

    settings = Settings(
        notes_dir=tmp_path,
        chroma_dir=tmp_path / "chroma",
        model_settings_dir=tmp_path / "model_settings",
    )
    container = _container(settings, notes, engine, history, ReviewAgent())
    client = TestClient(create_app(container))
    record = history.create("t")
    drafts.put(record.id, NoteDraft(
        action="create", file_name="Go.md", content="## 控制流\n\n",
    ))
    assert client.get(f"/conversations/{record.id}").json()["pending_draft"] is not None

    review = client.post(
        "/chat/review", json={"thread_id": record.id, "action": "reject"},
    )
    assert review.json() == {"status": "rejected"}
    assert client.get(f"/conversations/{record.id}").json()["pending_draft"] is None
    assert list(tmp_path.iterdir()) == []


def test_put_draft_saves_body_and_keeps_metadata(tmp_path: Path):
    """Editing a draft rewrites the body only; no note file changes."""
    client, history, notes, drafts = _draft_client(tmp_path)
    notes.create("Go.md", "Go")
    before = notes.read("Go.md")
    record = history.create("t")
    drafts.put(record.id, NoteDraft(
        action="append",
        file_name="Go.md",
        content="## 旧正文\n\n",
        reason="补一节",
        similar=["Go.md"],
        existing_files=["Go.md"],
    ))

    resp = client.put(
        "/chat/draft",
        json={"thread_id": record.id, "content": "## 新正文\n\n改过了。\n"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "updated"
    assert body["pending_draft"] == {
        "action": "append",
        "file_name": "Go.md",
        "content": "## 新正文\n\n改过了。\n",
        "reason": "补一节",
        "similar": ["Go.md"],
        "existing_files": ["Go.md"],
    }
    detail = client.get(f"/conversations/{record.id}").json()["pending_draft"]
    assert detail == body["pending_draft"]
    # 只改待审状态：正式笔记既没被写也没被新建。
    assert notes.read("Go.md") == before
    assert [path.name for path in tmp_path.glob("*.md")] == ["Go.md"]


def test_put_draft_without_pending_draft_returns_409(tmp_path: Path):
    client, history, _, _ = _draft_client(tmp_path)
    record = history.create("t")

    resp = client.put("/chat/draft", json={"thread_id": record.id, "content": "## x\n\n"})

    assert resp.status_code == 409
    assert history.get_pending_draft(record.id) is None


def test_put_draft_unknown_conversation_returns_404(tmp_path: Path):
    client, _, _, _ = _draft_client(tmp_path)

    resp = client.put(
        "/chat/draft",
        json={
            "thread_id": "00000000-0000-0000-0000-000000000001",
            "content": "## x\n\n",
        },
    )

    assert resp.status_code == 404


def test_put_draft_rejects_blank_content(tmp_path: Path):
    client, history, _, drafts = _draft_client(tmp_path)
    record = history.create("t")
    drafts.put(record.id, NoteDraft(action="create", file_name="Go.md", content="## x\n\n"))

    resp = client.put("/chat/draft", json={"thread_id": record.id, "content": "  \n"})

    assert resp.status_code == 422
    assert history.get_pending_draft(record.id)["content"] == "## x\n\n"


def test_put_draft_refuses_cross_origin(tmp_path: Path):
    client, history, _, drafts = _draft_client(tmp_path)
    record = history.create("t")
    drafts.put(record.id, NoteDraft(action="create", file_name="Go.md", content="## x\n\n"))

    resp = client.put(
        "/chat/draft",
        json={"thread_id": record.id, "content": "## 偷改\n\n"},
        headers={"origin": "https://evil.example", "host": "testserver"},
    )

    assert resp.status_code == 403
    assert history.get_pending_draft(record.id)["content"] == "## x\n\n"


def test_approve_after_draft_edit_writes_the_edited_body(tmp_path: Path):
    """The edited body is what approval commits; the draft then clears."""
    client, history, notes, drafts = _draft_client(tmp_path)
    record = history.create("t")
    drafts.put(record.id, NoteDraft(
        action="create", file_name="Go.md", content="## 原始提案\n\n",
    ))

    assert client.put(
        "/chat/draft",
        json={"thread_id": record.id, "content": "## 我改过的正文\n\n- 修正\n\n"},
    ).status_code == 200

    review = client.post("/chat/review", json={"thread_id": record.id, "action": "approve"})

    assert review.status_code == 200
    assert review.json()["status"] == "written"
    text = notes.read("Go.md")
    assert "## 我改过的正文" in text
    assert "原始提案" not in text
    assert history.get_pending_draft(record.id) is None


def test_override_after_draft_edit_appends_to_chosen_file(tmp_path: Path):
    """Override still works on an edited draft and keeps the original action."""
    client, history, notes, drafts = _draft_client(tmp_path)
    notes.create("A.md", "A")
    record = history.create("t")
    drafts.put(record.id, NoteDraft(
        action="create", file_name="C.md", content="## 要点\n\n- x\n\n",
    ))

    assert client.put(
        "/chat/draft",
        json={"thread_id": record.id, "content": "## 要点\n\n- x（改过）\n\n"},
    ).status_code == 200

    review = client.post("/chat/review", json={
        "thread_id": record.id,
        "action": "override",
        "write_action": "append",
        "file_name": "A.md",
    })

    assert review.json()["file_name"] == "A.md"
    assert "（改过）" in notes.read("A.md")
    assert not notes.exists("C.md")
    assert history.get_pending_draft(record.id) is None


def test_template_ships_resident_draft_actions_and_more_menu(tmp_path: Path):
    """草稿面板：常驻批准/拒绝，覆盖方式收进「更多操作」，覆盖表单默认不占位。"""
    client, _ = _client(tmp_path)
    html = client.get("/").text

    # 常驻操作与菜单触发器（运行时由 renderDraftActions 渲染，这里只钉住 hook 与文案）。
    assert 'data-act="approve"' in html
    assert 'data-act="reject"' in html
    assert 'data-act="more"' in html
    assert 'aria-haspopup="menu"' in html
    assert 'aria-expanded' in html
    assert "更多操作" in html
    assert "同意追加" in html and "同意覆盖" in html and "同意删除" in html and "同意新建" in html
    # 菜单项文案 + 菜单/表单容器默认隐藏，选择后才呈现。
    assert "追加到笔记" in html
    assert "新建笔记" in html
    assert 'id="citePaneMenu" role="menu" aria-label="更多草稿操作" hidden' in html
    assert 'id="citePaneForm" hidden' in html
    # 旧的常驻覆盖控件已移除：不再有同时占位的两个表单与「改为…」按钮。
    assert "改为追加到所选文件" not in html
    assert "改为新建文件" not in html


def test_template_ships_two_resize_handles_with_separator_aria(tmp_path: Path):
    """Chat 有左右两条分隔线，标记为可聚焦 separator，且不进入 Documents 视图。"""
    client, _ = _client(tmp_path)
    html = client.get("/").text

    assert 'id="conversationResizeHandle"' in html
    assert 'id="notePaneResizeHandle"' in html
    assert 'role="separator"' in html
    assert 'aria-orientation="vertical"' in html
    assert 'aria-valuemin="200"' in html
    assert 'aria-valuemax="400"' in html
    assert 'aria-valuemin="300"' in html
    assert 'aria-valuemax="600"' in html
    assert 'aria-valuenow' in html
    assert 'tabindex="0"' in html
    assert "noteagent.chat-layout.v1" in html
    # 初始 DOM：右栏分隔线随面板隐藏，宽度走 CSS 变量而不是硬编码百分比。
    assert 'id="notePaneResizeHandle"' in html and 'hidden></div>' in html
    assert "--sidebar-width" in html
    assert "--note-pane-width" in html
    # 分隔线只在 Chat 视图内，Documents 视图不包含。
    chat_view = html.split('id="viewChat"', 1)[1].split('id="viewDocs"', 1)[0]
    docs_view = html.split('id="viewDocs"', 1)[1]
    assert 'id="conversationResizeHandle"' in chat_view
    assert 'id="notePaneResizeHandle"' in chat_view
    assert 'id="conversationResizeHandle"' not in docs_view
    assert 'id="notePaneResizeHandle"' not in docs_view

