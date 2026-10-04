"""Production chat runs the checkpoint graph, not the legacy message table.

The legacy ``ConversationStore.append_message`` is sabotaged so any accidental write
is a hard failure, and every assertion reads the state back from the active head.
"""

from __future__ import annotations

import json

import pytest

from noteagent.model_management.schemas import ChatActivateIn, ChatProfileIn
from support.fakes import FakeChatModel
from support.webapp import build_checkpoint_app


def _parse_sse(text: str) -> list[tuple[str, str]]:
    events: list[tuple[str, str]] = []
    event, data = "message", None
    for line in text.splitlines():
        if line.startswith("event: "):
            event = line[7:].strip()
        elif line.startswith("data: "):
            data = line[6:]
        elif line.strip() == "":
            if data is not None:
                events.append((event, data))
            event, data = "message", None
    return events


def _event(events: list[tuple[str, str]], name: str):
    return [json.loads(data) for event, data in events if event == name]


def _sabotage_legacy_writes(app) -> None:
    """Any attempt to write the legacy message table now raises."""

    def boom(*args, **kwargs):
        raise AssertionError("legacy ConversationStore write path was used")

    app.history.append_message = boom
    app.history.append_tool_stub = boom


def test_http_chat_uses_checkpoint_without_legacy_message_writes(tmp_path):
    app = build_checkpoint_app(tmp_path, reply_batches=[["你好呀"]])
    _sabotage_legacy_writes(app)

    response = app.client.post("/chat", json={"question": "你好"})

    assert response.status_code == 200
    events = _parse_sse(response.text)
    conv = _event(events, "conversation")[0]
    assert _event(events, "user_message")[0]["message_id"]
    assert _event(events, "answer")[0] == "你好呀"
    assert _event(events, "turn_complete")[0]["status"] == "completed"

    # Message list now comes from the active checkpoint.
    messages = app.client.get(f"/conversations/{conv['id']}/messages").json()
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "你好"
    assert messages[1]["content"] == "你好呀"

    # And the legacy table stayed empty.
    assert app.history.list_messages(conv["id"]) == []


def test_restart_preserves_http_history_and_pending_draft(pg_checkpoint_app):
    from langchain_core.messages import AIMessage

    proposal = AIMessage(
        content="",
        tool_calls=[{
            "name": "propose_note",
            "args": {"action": "create", "file_name": "N.md", "content": "body"},
            "id": "c1",
        }],
    )
    app = pg_checkpoint_app(reply_batches=[[proposal, "好的"]])
    response = app.client.post("/chat", json={"question": "记一下"})
    assert response.status_code == 200
    conv_id = _event(_parse_sse(response.text), "conversation")[0]["id"]
    assert app.client.get(f"/conversations/{conv_id}").json()["pending_draft"]["file_name"] == "N.md"

    # Rebuild the container over the same schema: a genuine restart.
    restarted = pg_checkpoint_app(reply_batches=[], name="restart")

    messages = restarted.client.get(f"/conversations/{conv_id}/messages").json()
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "记一下"
    detail = restarted.client.get(f"/conversations/{conv_id}").json()
    assert detail["pending_draft"]["content"] == "body"


def test_duplicate_request_accepts_one_user_message(tmp_path):
    app = build_checkpoint_app(tmp_path, reply_batches=[["ok"]])
    first = app.client.post(
        "/chat", json={"question": "只接受一次", "request_id": "req-1"}
    )
    assert first.status_code == 200
    conv_id = _event(_parse_sse(first.text), "conversation")[0]["id"]

    second = app.client.post(
        "/chat",
        json={"question": "只接受一次", "conversation_id": conv_id, "request_id": "req-1"},
    )
    assert second.status_code == 409

    messages = app.client.get(f"/conversations/{conv_id}/messages").json()
    users = [m for m in messages if m["role"] == "user"]
    assert len(users) == 1


def test_switch_model_keeps_same_checkpoint_service(tmp_path):
    app = build_checkpoint_app(tmp_path, reply_batches=[["reply-1"], ["reply-2"]])
    first = app.client.post("/chat", json={"question": "q1"})
    conv_id = _event(_parse_sse(first.text), "conversation")[0]["id"]

    service_before = app.container.conversations
    revision = app.client.get("/model-settings").json()["revision"]
    switched = app.client.post(
        "/model-settings/chat/activate",
        json={
            "expected_revision": revision,
            "profile": {
                "label": "second",
                "provider": "openai-compatible",
                "model": "m2",
                "base_url": "http://localhost:9/v1",
                "auth_mode": "none",
            },
        },
    )
    assert switched.status_code == 200
    # The runtime was rebuilt, but the checkpoint store is the very same object.
    assert app.container.conversations is service_before

    second = app.client.post(
        "/chat", json={"question": "q2", "conversation_id": conv_id}
    )
    assert second.status_code == 200
    messages = app.client.get(f"/conversations/{conv_id}/messages").json()
    assert [m["content"] for m in messages] == ["q1", "reply-1", "q2", "reply-2"]


def test_message_list_exposes_identity_and_edit_reasons(tmp_path):
    app = build_checkpoint_app(
        tmp_path, reply_batches=[["same answer", "same answer"]]
    )
    first = app.client.post("/chat", json={"question": "重复"})
    conv_id = _event(_parse_sse(first.text), "conversation")[0]["id"]
    app.client.post("/chat", json={"question": "重复", "conversation_id": conv_id})

    messages = app.client.get(f"/conversations/{conv_id}/messages").json()
    users = [m for m in messages if m["role"] == "user"]
    assert [m["content"] for m in users] == ["重复", "重复"]
    # Identical text still gets two distinct server identities.
    assert len({m["id"] for m in users}) == 2
    assert all(m["turn_id"] for m in users)
    # Phase B is not implemented yet, so editing is disabled with a reason.
    assert all(m["editable"] is False for m in users)
    assert all(m["edit_unavailable_reason"] for m in users)

    refreshed = app.client.get(f"/conversations/{conv_id}/messages").json()
    assert [m["id"] for m in refreshed] == [m["id"] for m in messages]


def test_chat_rejects_unmigrated_legacy_conversation(tmp_path):
    app = build_checkpoint_app(tmp_path, reply_batches=[])
    legacy = app.history.create("legacy")
    response = app.client.post(
        "/chat", json={"question": "hi", "conversation_id": legacy.id}
    )
    assert response.status_code == 409
