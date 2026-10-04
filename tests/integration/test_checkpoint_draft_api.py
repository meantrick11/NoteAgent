"""Draft edits and reviews on a checkpoint conversation go through CAS state."""

from __future__ import annotations

import json

from langchain_core.messages import AIMessage

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


def _data(events, name):
    return [json.loads(d) for e, d in events if e == name]


def _proposal_draft(app, question: str = "记一下") -> str:
    """Run one turn that proposes a note; returns the conversation id."""
    response = app.client.post("/chat", json={"question": question})
    assert response.status_code == 200, response.text
    conv_id = _data(_parse_sse(response.text), "conversation")[0]["id"]
    assert app.client.get(f"/conversations/{conv_id}").json()["pending_draft"] is not None
    return conv_id


def _app_with_draft(tmp_path):
    proposal = AIMessage(
        content="",
        tool_calls=[{
            "name": "propose_note",
            "args": {"action": "create", "file_name": "N.md", "content": "orig body"},
            "id": "c1",
        }],
    )
    return build_checkpoint_app(tmp_path, reply_batches=[[proposal, "好的"]])


def test_draft_edit_is_checkpointed_and_stale_review_is_rejected(tmp_path):
    app = _app_with_draft(tmp_path)
    conv_id = _proposal_draft(app)

    updated = app.client.put(
        "/chat/draft",
        json={"thread_id": conv_id, "content": "edited body"},
    )
    assert updated.status_code == 200
    assert updated.json()["pending_draft"]["content"] == "edited body"
    # The draft lives in the checkpoint, not in the legacy pending_draft column.
    detail = app.client.get(f"/conversations/{conv_id}").json()
    assert detail["pending_draft"]["content"] == "edited body"

    # A review from a tab whose revision is stale is refused.
    stale = app.client.post(
        "/chat/review",
        json={"thread_id": conv_id, "action": "approve", "expected_revision": 99},
    )
    assert stale.status_code == 409
    assert not app.notes.exists("N.md")


def test_approve_writes_note_and_clears_draft(tmp_path):
    app = _app_with_draft(tmp_path)
    conv_id = _proposal_draft(app)

    app.client.put("/chat/draft", json={"thread_id": conv_id, "content": "edited body"})
    review = app.client.post(
        "/chat/review", json={"thread_id": conv_id, "action": "approve"}
    )
    assert review.status_code == 200
    assert review.json()["status"] == "written"
    assert "edited body" in app.notes.read("N.md")
    assert app.client.get(f"/conversations/{conv_id}").json()["pending_draft"] is None


def test_reject_clears_draft_without_writing(tmp_path):
    app = _app_with_draft(tmp_path)
    conv_id = _proposal_draft(app)

    review = app.client.post(
        "/chat/review", json={"thread_id": conv_id, "action": "reject"}
    )
    assert review.json()["status"] == "rejected"
    assert app.client.get(f"/conversations/{conv_id}").json()["pending_draft"] is None
    assert not app.notes.exists("N.md")


def test_draft_edit_without_pending_draft_is_409(tmp_path):
    app = build_checkpoint_app(tmp_path, reply_batches=[["no draft"]])

    response = app.client.post("/chat", json={"question": "hello"})
    conv_id = _data(_parse_sse(response.text), "conversation")[0]["id"]

    edit = app.client.put(
        "/chat/draft", json={"thread_id": conv_id, "content": "not allowed"}
    )
    assert edit.status_code == 409


def test_stale_tab_approval_is_rejected_with_real_revisions(tmp_path):
    app = _app_with_draft(tmp_path)
    conv_id = _proposal_draft(app)
    revision = app.client.get(f"/conversations/{conv_id}").json()["state_revision"]

    # Tab B saves the draft first, which advances the head revision.
    saved = app.client.put(
        "/chat/draft",
        json={"thread_id": conv_id, "content": "tabB body", "expected_revision": revision},
    )
    assert saved.status_code == 200
    new_revision = saved.json()["state_revision"]
    assert new_revision != revision

    # Tab A approves with its now-stale revision: refused, nothing written.
    stale = app.client.post(
        "/chat/review",
        json={"thread_id": conv_id, "action": "approve", "expected_revision": revision},
    )
    assert stale.status_code == 409
    assert not app.notes.exists("N.md")

    # With the current revision the approval succeeds and writes tab B's body.
    ok = app.client.post(
        "/chat/review",
        json={"thread_id": conv_id, "action": "approve", "expected_revision": new_revision},
    )
    assert ok.status_code == 200
    assert ok.json()["status"] == "written"
    assert "tabB body" in app.notes.read("N.md")


def test_busy_approval_has_no_file_or_draft_side_effect(tmp_path):
    import asyncio
    app = _app_with_draft(tmp_path)
    conv_id = _proposal_draft(app)
    prepared = asyncio.run(app.service.prepare_turn(conv_id, "next", "busy-approve"))
    before = asyncio.run(app.service.get_pending_draft(conv_id))
    response = app.client.post("/chat/review", json={
        "thread_id": conv_id, "action": "approve",
        "expected_revision": app.service.current_revision(conv_id),
    })
    assert response.status_code == 409
    assert not app.notes.exists("N.md")
    assert asyncio.run(app.service.get_pending_draft(conv_id)) == before
    assert app.service.get_active_run(conv_id)["run_id"] == prepared.run_id
