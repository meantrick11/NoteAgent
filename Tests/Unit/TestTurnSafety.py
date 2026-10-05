"""Accepted turns must survive concurrency and retryable preparation failures."""

import asyncio
import uuid

import pytest
from sqlalchemy import select

from NoteAgent.BusinessModules.ConversationState.ConversationModels import ConversationRun, UserMessageBoundary


async def test_second_request_is_rejected_while_first_prepare_is_pending(conversation_harness, monkeypatch):
    h = conversation_harness
    c = await h.create_conversation()
    original = h.service.read_state
    entered, release = asyncio.Event(), asyncio.Event()

    async def blocked_read(config):
        entered.set()
        await release.wait()
        return await original(config)

    monkeypatch.setattr(h.service, "read_state", blocked_read)
    first = asyncio.create_task(h.service.prepare_turn(c.id, "first", "first-request"))
    await entered.wait()
    second = asyncio.create_task(h.service.prepare_turn(c.id, "second", "second-request"))
    await asyncio.sleep(0)
    release.set()
    outcomes = await asyncio.gather(first, second, return_exceptions=True)
    assert sum(not isinstance(item, BaseException) for item in outcomes) == 1
    assert type(outcomes[1]).__name__ == "ConversationBusy"
    assert [m.content for m in await h.service.list_messages(c.id)] == ["first"]


async def test_saver_failure_allows_same_request_retry_without_duplicate_user(conversation_harness, monkeypatch):
    h = conversation_harness
    c = await h.create_conversation()
    original = h.runtime.saver.aput

    async def fail(*args, **kwargs):
        raise RuntimeError("saver unavailable")

    monkeypatch.setattr(h.runtime.saver, "aput", fail)
    with pytest.raises(RuntimeError, match="saver unavailable"):
        await h.service.prepare_turn(c.id, "retry", "retry-request")
    assert await h.service.list_messages(c.id) == []
    monkeypatch.setattr(h.runtime.saver, "aput", original)
    prepared = await h.service.prepare_turn(c.id, "retry", "retry-request")
    assert [m.content for m in await h.service.list_messages(c.id)] == ["retry"]
    with h.service._session_factory() as session:
        boundaries = session.scalars(select(UserMessageBoundary).where(UserMessageBoundary.conversation_id == uuid.UUID(c.id))).all()
        run = session.get(ConversationRun, uuid.UUID(prepared.run_id))
        assert len(boundaries) == 1
        assert run.checkpoint_id == h.active_head(c.id)["configurable"]["checkpoint_id"]


async def test_outdated_publish_cannot_replace_active_head(conversation_harness):
    h = conversation_harness
    c = await h.create_conversation()
    before = await h.service.get_state(c.id)
    branch = h.service.active_branch_id(c.id)
    candidate = await h.service.write_state(c.id, before.values, publish=False)
    await h.service.prepare_turn(c.id, "accepted", "newer-request")
    head = h.active_head(c.id)
    try:
        h.service.publish_head(c.id, branch, candidate["configurable"]["checkpoint_id"], expected_checkpoint_id=before.config["configurable"]["checkpoint_id"], expected_generation=0)
    except Exception as exc:
        assert type(exc).__name__ == "StaleConversation"
    else:
        pytest.fail("stale publisher replaced an accepted turn")
    assert h.active_head(c.id) == head


async def test_boundary_failure_keeps_user_invisible_and_request_retryable(conversation_harness, monkeypatch):
    from sqlalchemy import event
    h = conversation_harness
    c = await h.create_conversation()

    def fail_insert(*args):
        raise RuntimeError("boundary unavailable")

    event.listen(UserMessageBoundary, "before_insert", fail_insert)
    try:
        with pytest.raises(RuntimeError, match="boundary unavailable"):
            await h.service.prepare_turn(c.id, "retry", "boundary-request")
    finally:
        event.remove(UserMessageBoundary, "before_insert", fail_insert)
    assert await h.service.list_messages(c.id) == []
    await h.service.prepare_turn(c.id, "retry", "boundary-request")
    assert [m.content for m in await h.service.list_messages(c.id)] == ["retry"]
