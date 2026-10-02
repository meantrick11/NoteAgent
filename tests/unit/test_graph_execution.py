"""The run pointer must identify its own durable graph state, including failures."""

import uuid
import asyncio

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from sqlalchemy import select

from noteagent.chat.execution import execute_turn
from noteagent.chat.graph import build_chat_graph
from noteagent.conversations.models import ConversationRun


async def test_graph_ignores_newer_unpublished_saver_state(conversation_harness):
    h = conversation_harness
    c = await h.create_conversation()
    prepared = await h.service.prepare_turn(c.id, "accepted", "accepted-request")
    await h.fork_unpublished(c.id, prepared.config)
    h.model.replies = [AIMessage(content="answer")]
    graph = build_chat_graph(h.graph_runtime(), h.runtime.saver)
    async for _ in execute_turn(graph, h.service, prepared):
        pass
    assert [m.content for m in await h.service.list_messages(c.id)] == ["accepted", "answer"]


async def test_interrupted_graph_keeps_exact_tool_checkpoint_and_resumes(conversation_harness):
    h = conversation_harness
    c = await h.create_conversation()
    h.model.replies = [AIMessage(content="", tool_calls=[{"name": "propose_note", "id": "p1", "args": {"action": "create", "file_name": "A.md", "content": "proposal"}}])]
    prepared = await h.service.prepare_turn(c.id, "propose", "interrupted-request")
    graph = build_chat_graph(h.graph_runtime(), h.runtime.saver)
    with pytest.raises(AssertionError, match="ran out of scripted replies"):
        async for _ in execute_turn(graph, h.service, prepared):
            pass
    with h.service._session_factory() as session:
        run = session.get(ConversationRun, uuid.UUID(prepared.run_id))
        assert run.status == "interrupted"
        run_checkpoint = run.checkpoint_id
    from noteagent.conversations.checkpoints import thread_config
    state = await h.service.read_state(thread_config(c.id, run_checkpoint))
    assert state.values["pending_draft"]["content"] == "proposal"
    assert isinstance(state.values["runtime_messages"][-1], ToolMessage)
    # A newer unrelated candidate must not be selected during explicit resume.
    await h.fork_unpublished(c.id, prepared.config)
    h.model.replies = [AIMessage(content="proposal ready")]
    resumed = h.service.resume_turn(prepared.run_id)
    async for _ in execute_turn(graph, h.service, resumed, resume=True):
        pass
    assert [m.content for m in await h.service.list_messages(c.id)] == ["propose", "proposal ready"]
    with h.service._session_factory() as session:
        assert session.scalar(select(ConversationRun)).status == "completed"


async def test_completed_run_publishes_head_and_status_in_one_transaction(conversation_harness):
    from sqlalchemy import event
    h = conversation_harness
    c = await h.create_conversation()
    prepared = await h.service.prepare_turn(c.id, "question", "atomic-finish")
    initial_head = h.active_head(c.id)
    h.model.replies = [AIMessage(content="answer")]
    graph = build_chat_graph(h.graph_runtime(), h.runtime.saver)

    def reject_completed(connection, cursor, statement, parameters, context, executemany):
        bound = context.compiled_parameters[0] if context.compiled_parameters else {}
        if statement.startswith("UPDATE conversation_runs") and bound.get("status") == "completed":
            raise RuntimeError("completion unavailable")

    event.listen(h._engine, "before_cursor_execute", reject_completed)
    try:
        with pytest.raises(RuntimeError, match="completion unavailable"):
            async for _ in execute_turn(graph, h.service, prepared):
                pass
    finally:
        event.remove(h._engine, "before_cursor_execute", reject_completed)
    assert h.active_head(c.id) == initial_head


async def test_resume_refuses_changed_application_head(conversation_harness):
    h = conversation_harness
    c = await h.create_conversation()
    prepared = await h.service.prepare_turn(c.id, "question", "changed-head")
    graph = build_chat_graph(h.graph_runtime(), h.runtime.saver)
    with pytest.raises(AssertionError):
        async for _ in execute_turn(graph, h.service, prepared):
            pass
    view = await h.service.get_state(c.id)
    values = dict(view.values)
    values["pending_draft"] = {"file_name": "new.md", "content": "new draft"}
    await h.service.write_state(c.id, values, branch_id=prepared.branch_id, publish=True)
    from noteagent.conversations.service import StaleConversation
    with pytest.raises(StaleConversation):
        h.service.resume_turn(prepared.run_id)


async def test_expired_preparation_is_reclaimed_without_touching_live_worker(conversation_harness, monkeypatch):
    from datetime import datetime, timezone, timedelta
    h = conversation_harness
    c = await h.create_conversation()
    original = h.service.read_state
    entered, release = asyncio.Event(), asyncio.Event()
    async def blocked(config):
        entered.set()
        await release.wait()
        return await original(config)
    monkeypatch.setattr(h.service, "read_state", blocked)
    first = asyncio.create_task(h.service.prepare_turn(c.id, "lost", "lost-preparation"))
    await entered.wait()
    with h.service._session_factory() as session:
        run = session.scalar(select(ConversationRun))
        run.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()
    try:
        h.service.reconcile_expired_runs()
    finally:
        release.set()
    with pytest.raises(Exception):
        await first
    monkeypatch.setattr(h.service, "read_state", original)
    prepared = await h.service.prepare_turn(c.id, "retry", "lost-preparation")
    h.service.reconcile_expired_runs()
    with h.service._session_factory() as session:
        assert session.get(ConversationRun, uuid.UUID(prepared.run_id)).status == "running"
    assert [m.content for m in await h.service.list_messages(c.id)] == ["retry"]


async def test_close_waits_for_model_cleanup_before_resume_is_allowed(conversation_harness, monkeypatch):
    h = conversation_harness
    c = await h.create_conversation()
    prepared = await h.service.prepare_turn(c.id, "question", "close-request")
    entered, closed = asyncio.Event(), asyncio.Event()
    async def blocking_model(messages, config=None):
        entered.set()
        try:
            await asyncio.Event().wait()
            yield AIMessage(content="unreachable")
        finally:
            closed.set()
    monkeypatch.setattr(h.model, "astream", blocking_model)
    graph = build_chat_graph(h.graph_runtime(), h.runtime.saver)
    stream = execute_turn(graph, h.service, prepared)
    await anext(stream)
    await entered.wait()
    await stream.aclose()
    assert closed.is_set()
    with h.service._session_factory() as session:
        assert session.get(ConversationRun, uuid.UUID(prepared.run_id)).status == "interrupted"


async def test_abandoned_accepted_turn_can_resume_before_first_graph_node(conversation_harness):
    from datetime import datetime, timezone, timedelta
    h = conversation_harness
    c = await h.create_conversation()
    prepared = await h.service.prepare_turn(c.id, "question", "never-started")
    with h.service._session_factory() as session:
        run = session.get(ConversationRun, uuid.UUID(prepared.run_id))
        run.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()
    h.service.reconcile_expired_runs()
    resumed = h.service.resume_turn(prepared.run_id)
    h.model.replies = [AIMessage(content="answer")]
    graph = build_chat_graph(h.graph_runtime(), h.runtime.saver)
    async for _ in execute_turn(graph, h.service, resumed, resume=True):
        pass
    assert [m.content for m in await h.service.list_messages(c.id)] == ["question", "answer"]
