import json
from pathlib import Path

from fastapi.testclient import TestClient

from noteagent.bootstrap.app import AppContainer, create_app
from noteagent.bootstrap.settings import Settings
from noteagent.chat.history import ConversationStore, start_turn
from noteagent.db import Base, create_engine_from_url, create_session_factory
from noteagent.notes.repository import FileNoteRepository
from noteagent.web import read_home_html


class FakeAgent:
    async def stream(self, question: str, thread_id: str, turn_id: str | None = None):
        yield {"event": "token", "data": f"echo:{question}"}
        yield {"event": "assistant_final", "data": f"echo:{question}"}

    def review(self, thread_id: str, action: str, write_action=None, file_name=None):
        return {"status": "rejected"} if action == "reject" else {"status": "written", "file_name": "Go.md"}


def _sqlite_history():
    engine = create_engine_from_url("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine, ConversationStore(create_session_factory(engine))


def _client(tmp_path: Path) -> tuple[TestClient, ConversationStore]:
    settings = Settings(notes_dir=tmp_path, chroma_dir=tmp_path / "chroma")
    engine, history = _sqlite_history()
    container = AppContainer(
        settings=settings,
        notes=FileNoteRepository(tmp_path),
        retrieval=None,  # type: ignore[arg-type]
        chat_agent=FakeAgent(),  # type: ignore[arg-type]
        engine=engine,
        history=history,
    )
    return TestClient(create_app(container)), history


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
    assert read_home_html() == response.text


def test_chat_and_review_routes(tmp_path: Path):
    client, history = _client(tmp_path)
    record = history.create("t")
    chat = client.post("/chat", json={"question": "你好", "thread_id": record.id})
    assert chat.status_code == 200
    assert chat.headers["content-type"].startswith("text/event-stream")
    assert "event: conversation" in chat.text
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


def test_chat_persists_final_assistant_not_tool_hop_tokens(tmp_path: Path):
    class FakeToolHopAgent:
        async def stream(self, question: str, thread_id: str, turn_id: str | None = None):
            yield {"event": "token", "data": "calling-tool"}
            yield {"event": "assistant_final", "data": "done"}

        def review(self, thread_id: str, action: str, write_action=None, file_name=None):
            return {"status": "rejected"}

    settings = Settings(notes_dir=tmp_path, chroma_dir=tmp_path / "chroma")
    engine, history = _sqlite_history()
    container = AppContainer(
        settings=settings,
        notes=FileNoteRepository(tmp_path),
        retrieval=None,  # type: ignore[arg-type]
        chat_agent=FakeToolHopAgent(),  # type: ignore[arg-type]
        engine=engine,
        history=history,
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
