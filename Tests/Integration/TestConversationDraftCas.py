"""Draft-mutation CAS defects found in the phase-A review.

S1: a draft edit must not move the head while a turn owns the conversation.
R1: a draft edit must be published against the head it was read from, so an
interleaved publish is rejected instead of silently overwritten.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage

from NoteAgent.BusinessModules.ConversationState.ConversationCheckpoints import checkpoint_id_of
from NoteAgent.BusinessModules.ConversationState.ConversationContracts import ConversationBusy, StaleConversation
from Support.Fakes import FakeChatModel


def _proposal() -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{
            "name": "propose_note",
            "args": {"action": "create", "file_name": "N.md", "content": "body"},
            "id": "c1",
        }],
    )


async def _conversation_with_draft(harness):
    """A checkpoint conversation holding one pending draft."""
    harness.model = FakeChatModel([_proposal(), "ok"])
    record = await harness.create_conversation("t")
    await harness.complete_turn(record.id, "记一下")
    draft = await harness.service.get_pending_draft(record.id)
    assert draft is not None
    return record


async def test_draft_edit_refused_while_a_turn_owns_the_conversation(conversation_harness):
    h = conversation_harness
    record = await _conversation_with_draft(h)

    # A new question is accepted; the run now owns the conversation.
    prepared = await h.service.prepare_turn(record.id, "新问题", request_id="r1")
    assert prepared.request_id == "r1"

    with pytest.raises(ConversationBusy):
        await h.service.update_pending_draft(record.id, "edited while running")

    # The draft is unchanged and the accepted user message is still there.
    assert (await h.service.get_pending_draft(record.id))["content"] == "body"


async def test_draft_edit_from_a_stale_view_is_rejected(postgres_harness):
    h = postgres_harness
    record = await _conversation_with_draft(h)

    stale_view = await h.service.get_state(record.id)
    branch_id = h.service.active_branch_id(record.id)

    # Another publisher moves the head (a newer summary) after the view was read.
    moved = dict(stale_view.values)
    moved["running_summary"] = "NEW SUMMARY"
    await h.service.write_state(
        record.id, moved, branch_id=branch_id,
        parent_checkpoint_id=checkpoint_id_of(stale_view.config), publish=True,
    )

    updated = dict(stale_view.values)
    updated["pending_draft"] = {"action": "create", "file_name": "N.md", "content": "stale edit"}
    with pytest.raises(StaleConversation):
        await h.service._republish_state(
            record.id, stale_view, {"pending_draft": updated["pending_draft"]},
            h.service.current_revision(record.id),
        )

    # The interleaved publish is preserved, not clobbered by the stale edit.
    current = await h.service.get_state(record.id)
    assert current.values["running_summary"] == "NEW SUMMARY"
    assert current.values["pending_draft"]["content"] == "body"


async def test_review_holds_postgres_permission_during_saver_await(postgres_harness):
    """A second DB session cannot claim a turn between validation and file IO."""
    import asyncio
    h = postgres_harness
    record = await _conversation_with_draft(h)
    saver = h.runtime.saver
    original = saver.aput
    entered = asyncio.Event()
    release = asyncio.Event()
    writes = []

    async def paused(*args, **kwargs):
        entered.set()
        await release.wait()
        return await original(*args, **kwargs)

    saver.aput = paused
    review = asyncio.create_task(h.service.review_pending_draft(
        record.id, lambda draft: writes.append(draft["content"]) or {"status": "written"},
    ))
    try:
        await asyncio.wait_for(entered.wait(), 3)
        with pytest.raises(ConversationBusy):
            await h.service.prepare_turn(record.id, "competing question", "review-competing")
        assert writes == []
        release.set()
        assert (await review)["status"] == "written"
        assert writes == ["body"]
        assert await h.service.get_pending_draft(record.id) is None
    finally:
        release.set()
        saver.aput = original
        await review


async def test_review_saver_failure_does_not_invoke_writer(conversation_harness):
    h = conversation_harness
    record = await _conversation_with_draft(h)
    original = h.runtime.saver.aput
    writes = []

    async def fail(*args, **kwargs):
        raise RuntimeError("saver unavailable")

    h.runtime.saver.aput = fail
    try:
        with pytest.raises(RuntimeError, match="saver unavailable"):
            await h.service.review_pending_draft(
                record.id, lambda draft: writes.append(draft) or {"status": "written"},
            )
    finally:
        h.runtime.saver.aput = original
    assert writes == []
    assert await h.service.get_pending_draft(record.id) is not None


async def test_metadata_route_keeps_event_loop_live_during_review(postgres_harness):
    import asyncio
    from types import SimpleNamespace
    from sqlalchemy import event
    from NoteAgent.HttpApi.ConversationApi.ConversationRoutes import rename_conversation
    from NoteAgent.HttpApi.ConversationApi.ConversationSchemas import RenameConversation
    h = postgres_harness
    record = await _conversation_with_draft(h)
    original = h.service.read_state
    entered, release = asyncio.Event(), asyncio.Event()

    def limit_lock_wait(connection, record, proxy):
        with connection.cursor() as cursor:
            cursor.execute("SET lock_timeout = '300ms'")

    async def paused(config):
        entered.set()
        await release.wait()
        return await original(config)

    event.listen(h._engine, "checkout", limit_lock_wait)
    h.service.read_state = paused
    review = asyncio.create_task(h.service.review_pending_draft(record.id, lambda draft: {"status": "rejected"}))
    timer = None
    try:
        await asyncio.wait_for(entered.wait(), 3)
        timer = asyncio.get_running_loop().call_later(0.03, release.set)
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(container=SimpleNamespace(history=h.history))))
        renamed = await rename_conversation(record.id, RenameConversation(title="renamed"), request)
        assert renamed.title == "renamed"
        assert release.is_set()
        await review
    finally:
        release.set()
        if timer:
            timer.cancel()
        h.service.read_state = original
        event.remove(h._engine, "checkout", limit_lock_wait)
        await review
