"""Draft edits and reviews on a checkpoint conversation go through CAS state."""

from __future__ import annotations

import json

from langchain_core.messages import AIMessage

from NoteAgent.BusinessModules.ChatAgent.WebReading import WebPageResult
from Support.Fakes import FakeWebReader
from Support.Webapp import build_checkpoint_app


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

async def test_optional_revision_does_not_reuse_different_approvals(tmp_path):
    from NoteAgent.TechnicalSupport.DatabaseAccess import create_session_factory
    from NoteAgent.TechnicalSupport.NoteAccessControl.NoteAccessGate import WorkspaceGate
    from NoteAgent.BusinessModules.NoteStorage.NoteVersions import NoteVersionStore
    from NoteAgent.BusinessModules.NoteStorage.NoteChanges import NoteMutationService
    app = _app_with_draft(tmp_path / 'app')
    cid = _proposal_draft(app)
    from NoteAgent.BusinessModules.NoteStorage.MarkdownRepository import FileNoteRepository
    app.notes = FileNoteRepository(tmp_path / 'notes')
    app.container.notes = app.notes
    factory = create_session_factory(app.container.engine)
    gate = WorkspaceGate(factory); gate.ensure_row()
    mutations = NoteMutationService(app.notes, NoteVersionStore(tmp_path / 'history', app.notes.root), gate, factory)
    from NoteAgent.ApplicationFlows.DraftApproval.DraftApprovalWorkflow import DraftApprovalWorkflow
    app.container.chat_agent._approvals = DraftApprovalWorkflow(
        service=app.service, notes=app.notes, legacy_drafts=app.drafts,
        mutations=mutations,
    )
    response = app.client.post('/chat/review', json={'thread_id': cid, 'action': 'approve'})
    assert response.status_code == 200, response.text
    assert response.json().get('status') == 'written', response.text
    state = dict((await app.service.get_state(cid)).values)
    state['pending_draft'] = {'action': 'create', 'file_name': 'Other.md', 'content': 'second'}
    await app.service.write_state(cid, state, publish=True, branch_id=state["branch_id"])
    response = app.client.post('/chat/review', json={'thread_id': cid, 'action': 'approve'})
    assert response.status_code == 200, response.text
    assert response.json().get('status') == 'written', response.text
    assert app.notes.exists('Other.md')


async def test_cancelled_approval_keeps_durable_maintenance_and_startup_finishes(tmp_path, monkeypatch):
    import asyncio
    from Support.DurableApp import build_durable_app
    from NoteAgent.AppBootstrap.HttpApp import lifespan
    app = build_durable_app(tmp_path)
    cid = (await app.service.create_conversation('approval')).id
    state = dict((await app.service.get_state(cid)).values)
    state['pending_draft'] = {'action': 'create', 'file_name': 'N.md', 'content': 'once'}
    await app.service.write_state(cid, state, publish=True, branch_id=state['branch_id'])
    original = app.service.write_state
    calls = 0
    async def cancelled(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise asyncio.CancelledError()
        return await original(*args, **kwargs)
    monkeypatch.setattr(app.service, 'write_state', cancelled)
    import pytest
    with pytest.raises(asyncio.CancelledError):
        await app.container.chat_agent.review(cid, 'approve')
    assert app.notes.exists('N.md')
    assert app.container.workspace.maintenance()[1] == 'approval'
    assert (await app.service.get_pending_draft(cid)) is not None
    monkeypatch.setattr(app.service, 'write_state', original)
    async with lifespan(app.client.app):
        assert app.container.workspace.maintenance() is None
        assert await app.service.get_pending_draft(cid) is None
        assert app.notes.read('N.md').count('once') == 1
        assert app.container.mutations._repairs.is_synced('N.md', app.container.retrieval)


# ---- webpage sources in the draft and the written note (REQ-009) ----------------

U1 = "https://example.com/gil"
U2 = "https://example.com/rust"
U3 = "https://example.com/timeout"


def _page(url: str, *, status: str = "ok", title=None, content: str = "", error=None) -> WebPageResult:
    return WebPageResult(
        url=url,
        final_url=url if status in ("ok", "partial") else None,
        status=status,
        title=title,
        content=content,
        error=error,
    )


def _read_message(*urls: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {"name": "read_webpage", "id": f"w{index}", "args": {"url": url}}
            for index, url in enumerate(urls)
        ],
    )


def _propose_message(action: str, file_name: str, content: str, **extra) -> AIMessage:
    if "source_urls" in extra or "user_supplied_source_urls" in extra:
        extra.setdefault("source_urls", [])
        extra.setdefault("user_supplied_source_urls", [])
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "propose_note",
                "id": "p1",
                "args": {"action": action, "file_name": file_name, "content": content, **extra},
            }
        ],
    )


def _run_turn(app, question: str) -> str:
    response = app.client.post("/chat", json={"question": question})
    assert response.status_code == 200, response.text
    return _data(_parse_sse(response.text), "conversation")[0]["id"]


def _draft(app, conv_id: str) -> dict:
    draft = app.client.get(f"/conversations/{conv_id}").json()["pending_draft"]
    assert draft is not None
    return draft


def test_web_sources_listed_deduped_in_order_and_written_verbatim(tmp_path):
    reader = FakeWebReader(
        {U1: _page(U1, title="GIL", content="锁。"), U2: _page(U2, title="Rust", content="所有权。")}
    )
    app = build_checkpoint_app(
        tmp_path,
        reply_batches=[[
            _read_message(U1, U2),
            _propose_message("create", "GIL.md", "## GIL\n\n锁。", source_urls=[U1, U1, U2]),
            "草稿已生成",
        ]],
        web_reader=reader,
    )
    conv = _run_turn(app, f"读 {U1} 和 {U2} 后整理成笔记")

    draft = _draft(app, conv)
    assert draft["source_urls"] == [U1, U2]
    assert draft["content"].count("## 来源") == 1
    assert draft["content"].index(f"- {U1}") < draft["content"].index(f"- {U2}")

    review = app.client.post("/chat/review", json={"thread_id": conv, "action": "approve"})
    assert review.json()["status"] == "written"
    # The written file is exactly the auto title plus the approved draft body.
    assert app.notes.read("GIL.md") == "# GIL\n\n" + draft["content"]


def test_plain_note_has_no_source_section(tmp_path):
    app = build_checkpoint_app(
        tmp_path,
        reply_batches=[[_propose_message("create", "A.md", "## A\n\n正文。"), "ok"]],
        web_reader=FakeWebReader({}),
    )
    conv = _run_turn(app, "把这段整理成笔记")

    draft = _draft(app, conv)
    assert "## 来源" not in draft["content"]
    assert draft["source_urls"] == []


def test_url_that_was_not_read_is_not_written_as_a_source(tmp_path):
    reader = FakeWebReader({U3: _page(U3, status="failed", error="请求超时")})
    app = build_checkpoint_app(
        tmp_path,
        reply_batches=[[
            _read_message(U3),
            _propose_message("create", "T.md", "## T\n\n正文。", source_urls=[U3]),
            "ok",
        ]],
        web_reader=reader,
    )
    conv = _run_turn(app, f"读 {U3} 后整理")

    draft = _draft(app, conv)
    assert draft["source_urls"] == []
    assert "## 来源" not in draft["content"]


def test_user_pasted_body_marks_the_failed_source(tmp_path):
    reader = FakeWebReader({U3: _page(U3, status="failed", error="timeout")})
    app = build_checkpoint_app(
        tmp_path,
        reply_batches=[[_read_message(U3), "Please paste the article text."]],
        web_reader=reader,
    )
    conv = _run_turn(app, f"Read {U3}")
    app.model.replies.extend([
        _propose_message("create", "T.md", "## T\n\nPasted body.", user_supplied_source_urls=[U3]),
        AIMessage(content="Draft ready"),
    ])
    pasted = "Here is the article body: " + ("Detailed original page content. " * 4)
    response = app.client.post("/chat", json={"conversation_id": conv, "question": pasted})
    assert response.status_code == 200
    draft = _draft(app, conv)
    assert draft["user_supplied_source_urls"] == [U3]
    assert U3 in draft["content"]


def test_failed_page_is_not_marked_user_provided_without_later_paste(tmp_path):
    reader = FakeWebReader({U3: _page(U3, status="failed", error="timeout")})
    app = build_checkpoint_app(
        tmp_path,
        reply_batches=[[
            _read_message(U3),
            _propose_message("create", "T.md", "## T\n\nInvented body.", user_supplied_source_urls=[U3]),
            "Draft ready",
        ]],
        web_reader=reader,
    )
    conv = _run_turn(app, f"Read {U3}; I will paste it later")
    draft = _draft(app, conv)
    assert draft["user_supplied_source_urls"] == []
    assert U3 not in draft["content"]


def test_editing_a_web_draft_keeps_the_source_section(tmp_path):
    reader = FakeWebReader({U1: _page(U1, title="GIL", content="锁。")})
    app = build_checkpoint_app(
        tmp_path,
        reply_batches=[[
            _read_message(U1),
            _propose_message("create", "GIL.md", "## GIL\n\n锁。", source_urls=[U1]),
            "ok",
        ]],
        web_reader=reader,
    )
    conv = _run_turn(app, f"读 {U1} 后整理")

    edited = app.client.put(
        "/chat/draft", json={"thread_id": conv, "content": "## GIL\n\n改过的正文。"}
    )
    body = edited.json()["pending_draft"]["content"]
    assert "改过的正文" in body
    assert body.count("## 来源") == 1
    assert U1 in body

    review = app.client.post("/chat/review", json={"thread_id": conv, "action": "approve"})
    assert review.json()["status"] == "written"
    assert app.notes.read("GIL.md") == "# GIL\n\n" + body


def test_replace_merges_into_a_single_trailing_source_section(tmp_path):
    reader = FakeWebReader({U2: _page(U2, title="Rust", content="所有权。")})
    old = "# GIL\n\n## 旧\n\n旧正文。\n\n## 来源\n\n- https://old.test/x\n"
    app = build_checkpoint_app(
        tmp_path,
        reply_batches=[[
            _read_message(U2),
            _propose_message(
                "replace", "GIL.md",
                "# GIL\n\n## 旧\n\n旧正文。\n\n## 来源\n\n- https://old.test/x\n",
                source_urls=[U2],
            ),
            "ok",
        ]],
        web_reader=reader,
    )
    app.notes.create("GIL.md", "GIL")
    app.notes.write("GIL.md", old[len("# GIL\n\n"):], append=True)

    conv = _run_turn(app, f"用 {U2} 更新 GIL.md")

    draft = _draft(app, conv)
    assert draft["content"].count("## 来源") == 1
    assert "https://old.test/x" in draft["content"]
    assert U2 in draft["content"]


def test_append_to_sourced_note_previews_and_writes_one_merged_source_section(tmp_path):
    reader = FakeWebReader({U2: _page(U2, content="Rust ownership details")})
    app = build_checkpoint_app(
        tmp_path,
        reply_batches=[[
            _read_message(U2),
            _propose_message("append", "GIL.md", "\n## New\n\nRust details.\n", source_urls=[U2]),
            "Draft ready",
        ]],
        web_reader=reader,
    )
    app.notes.create("GIL.md", "GIL")
    app.notes.write("GIL.md", "## Old\n\nOld details.\n\n## 来源\n\n- https://old.test/x\n")

    conv = _run_turn(app, f"Combine {U2} into GIL.md")
    draft = _draft(app, conv)
    assert draft["action"] == "replace"
    assert draft["content"].count("## 来源") == 1
    assert draft["content"].index("Old details") < draft["content"].index("Rust details")
    assert draft["content"].index("https://old.test/x") < draft["content"].index(U2)
    assert draft["content"].rstrip().endswith(f"- {U2}")
    review = app.client.post("/chat/review", json={"thread_id": conv, "action": "approve"})
    assert review.json()["status"] == "written"
    assert app.notes.read("GIL.md") == draft["content"]


def test_web_source_survives_read_then_note_in_next_turn(tmp_path):
    reader = FakeWebReader({U1: _page(U1, content="GIL details")})
    app = build_checkpoint_app(
        tmp_path,
        reply_batches=[[
            _read_message(U1), "I read it."
        ]],
        web_reader=reader,
    )
    conv = _run_turn(app, f"Read {U1}")
    app.model.replies.extend([
        _propose_message("create", "GIL.md", "## GIL\n\nDetails.", source_urls=[U1]),
        AIMessage(content="Draft ready"),
    ])
    response = app.client.post("/chat", json={"conversation_id": conv, "question": "Make a note from that page"})
    assert response.status_code == 200
    assert U1 in _draft(app, conv)["content"]


def test_web_note_without_explicit_source_selection_is_rejected(tmp_path):
    reader = FakeWebReader({U1: _page(U1, content="GIL details")})
    app = build_checkpoint_app(
        tmp_path,
        reply_batches=[[
            _read_message(U1),
            _propose_message("create", "GIL.md", "## GIL\n\nDetails."),
            "Done",
        ]],
        web_reader=reader,
    )
    conv = _run_turn(app, f"Make a note from {U1}")
    assert app.client.get(f"/conversations/{conv}").json()["pending_draft"] is None


def test_web_note_with_only_one_source_field_is_rejected(tmp_path):
    reader = FakeWebReader({U1: _page(U1, content="GIL details")})
    incomplete = AIMessage(content="", tool_calls=[{
        "name": "propose_note", "id": "p1",
        "args": {"action": "create", "file_name": "GIL.md", "content": "## GIL\n\nDetails.",
                 "user_supplied_source_urls": []},
    }])
    app = build_checkpoint_app(
        tmp_path,
        reply_batches=[[_read_message(U1), incomplete, "Done"]],
        web_reader=reader,
    )
    conv = _run_turn(app, f"Make a note from {U1}")
    assert app.client.get(f"/conversations/{conv}").json()["pending_draft"] is None


def test_delete_draft_does_not_need_web_source_fields(tmp_path):
    reader = FakeWebReader({U1: _page(U1, content="GIL details")})
    app = build_checkpoint_app(
        tmp_path,
        reply_batches=[[_read_message(U1), _propose_message("delete", "GIL.md", ""), "Done"]],
        web_reader=reader,
    )
    app.notes.create("GIL.md", "GIL")
    conv = _run_turn(app, f"Read {U1} and delete GIL.md")
    assert _draft(app, conv)["action"] == "delete"


def test_rejecting_a_web_draft_writes_nothing(tmp_path):
    reader = FakeWebReader({U1: _page(U1, title="GIL", content="锁。")})
    app = build_checkpoint_app(
        tmp_path,
        reply_batches=[[
            _read_message(U1),
            _propose_message("create", "GIL.md", "## GIL\n\n锁。", source_urls=[U1]),
            "ok",
        ]],
        web_reader=reader,
    )
    conv = _run_turn(app, f"读 {U1} 后整理")

    review = app.client.post("/chat/review", json={"thread_id": conv, "action": "reject"})
    assert review.json()["status"] == "rejected"
    assert not app.notes.exists("GIL.md")
