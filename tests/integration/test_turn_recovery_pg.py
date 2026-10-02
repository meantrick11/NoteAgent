"""Turn claims and interrupted graph state must survive real PostgreSQL reopen."""

import asyncio
import uuid

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from sqlalchemy import select

from noteagent.chat.execution import execute_turn
from noteagent.chat.graph import build_chat_graph
from noteagent.conversations.checkpoints import thread_config
from noteagent.conversations.models import ConversationRun
from noteagent.conversations.service import ConversationBusy, ConversationService
from support.fakes import FakeChatModel


async def test_two_service_instances_cannot_claim_same_conversation(postgres_harness, monkeypatch):
    h = postgres_harness
    c = await h.create_conversation()
    other = ConversationService(h.service._session_factory, h.runtime)
    entered, release = asyncio.Event(), asyncio.Event()
    original = h.service.read_state

    async def blocked(config):
        entered.set()
        await release.wait()
        return await original(config)

    monkeypatch.setattr(h.service, "read_state", blocked)
    pending = asyncio.create_task(h.service.prepare_turn(c.id, "first", "first-pg"))
    await entered.wait()
    try:
        with pytest.raises(ConversationBusy):
            await other.prepare_turn(c.id, "second", "second-pg")
    finally:
        release.set()
        await pending
    assert [m.content for m in await h.service.list_messages(c.id)] == ["first"]


async def test_real_graph_tool_checkpoint_survives_reopen_and_resume(postgres_harness):
    h = postgres_harness
    c = await h.create_conversation()
    h.model = FakeChatModel([AIMessage(content="", tool_calls=[{"name": "propose_note", "id": "p1", "args": {"action": "create", "file_name": "A.md", "content": "persistent proposal"}}])])
    prepared = await h.service.prepare_turn(c.id, "propose", "reopen-pg")
    graph = build_chat_graph(h.graph_runtime(), h.runtime.saver)
    with pytest.raises(AssertionError, match="ran out of scripted replies"):
        async for _ in execute_turn(graph, h.service, prepared):
            pass
    await h.reopen()
    with h.service._session_factory() as session:
        run = session.get(ConversationRun, uuid.UUID(prepared.run_id))
        assert run.status == "interrupted"
        checkpoint_id = run.checkpoint_id
    view = await h.service.read_state(thread_config(c.id, checkpoint_id))
    assert view.values["pending_draft"]["content"] == "persistent proposal"
    assert isinstance(view.values["runtime_messages"][-1], ToolMessage)
    resumed = h.service.resume_turn(prepared.run_id)
    h.model.replies = [AIMessage(content="ready")]
    graph = build_chat_graph(h.graph_runtime(), h.runtime.saver)
    async for _ in execute_turn(graph, h.service, resumed, resume=True):
        pass
    assert [m.content for m in await h.service.list_messages(c.id)] == ["propose", "ready"]
    with h.service._session_factory() as session:
        assert session.scalar(select(ConversationRun)).status == "completed"


def test_new_migration_excludes_duplicate_active_runs(pg_target, monkeypatch):
    from pathlib import Path
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect
    from noteagent.db import create_engine_from_url
    config = Config(str(Path("alembic.ini").resolve()))
    # env.py resolves Settings itself; pin that source too, never migrate public.
    monkeypatch.setenv("DATABASE_URL", pg_target.sqlalchemy_url)
    config.set_main_option("sqlalchemy.url", pg_target.sqlalchemy_url.replace("%", "%%"))
    command.upgrade(config, "head")
    engine = create_engine_from_url(pg_target.sqlalchemy_url)
    try:
        indexes = inspect(engine).get_indexes("conversation_runs")
        assert any(item["name"] == "uq_conversation_runs_active" and item["unique"] for item in indexes)
        command.downgrade(config, "b1e7c4a90d23")
        assert all(item["name"] != "uq_conversation_runs_active" for item in inspect(engine).get_indexes("conversation_runs"))
    finally:
        engine.dispose()


async def test_uncaught_process_loss_is_reconciled_after_lease_expiry(postgres_harness):
    from datetime import datetime, timezone, timedelta
    h = postgres_harness
    c = await h.create_conversation()
    prepared = await h.service.prepare_turn(c.id, "accepted before crash", "crash-pg")
    # No executor exception handler runs: leave the committed running record.
    with h.service._session_factory() as session:
        run = session.get(ConversationRun, uuid.UUID(prepared.run_id))
        run.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()
    await h.reopen()
    h.service.reconcile_expired_runs()
    with h.service._session_factory() as session:
        assert session.get(ConversationRun, uuid.UUID(prepared.run_id)).status == "interrupted"
    assert h.model.calls == []
    resumed = h.service.resume_turn(prepared.run_id)
    h.model.replies = [AIMessage(content="resumed answer")]
    graph = build_chat_graph(h.graph_runtime(), h.runtime.saver)
    async for _ in execute_turn(graph, h.service, resumed, resume=True):
        pass
    assert [m.content for m in await h.service.list_messages(c.id)] == ["accepted before crash", "resumed answer"]


async def test_stale_completion_cannot_overwrite_a_new_resume_lease(postgres_harness):
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import event
    from noteagent.conversations.service import StaleConversation
    h = postgres_harness
    c = await h.create_conversation()
    prepared = await h.service.prepare_turn(c.id, "question", "lease-race")
    head = h.active_head(c.id)
    values = dict((await h.service.get_state(c.id)).values)
    values["run_status"] = "completed"
    saved = await h.service.write_state(c.id, values, publish=False)
    with h.service._session_factory() as session:
        run = session.get(ConversationRun, uuid.UUID(prepared.run_id))
        run.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()
    resumed = []
    def steal_lease(connection, cursor, statement, parameters, context, executemany):
        bound = context.compiled_parameters[0] if context.compiled_parameters else {}
        if not resumed and statement.startswith("UPDATE conversation_runs") and bound.get("status") == "completed":
            h.service.reconcile_expired_runs()
            resumed.append(h.service.resume_turn(prepared.run_id))
    event.listen(h._engine, "before_cursor_execute", steal_lease)
    try:
        with pytest.raises(StaleConversation):
            h.service.finish_run(prepared, saved["configurable"]["checkpoint_id"], "completed")
    finally:
        event.remove(h._engine, "before_cursor_execute", steal_lease)
    assert h.active_head(c.id) == head
    with h.service._session_factory() as session:
        run = session.get(ConversationRun, uuid.UUID(prepared.run_id))
        assert run.status == "running"
        assert run.lease_token == resumed[0].lease_token


def test_migration_refuses_legacy_active_claims_without_deleting_them(pg_target, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text
    from noteagent.db import create_engine_from_url
    monkeypatch.setenv("DATABASE_URL", pg_target.sqlalchemy_url)
    config = Config("alembic.ini")
    command.upgrade(config, "b1e7c4a90d23")
    engine = create_engine_from_url(pg_target.sqlalchemy_url)
    c_id, run_id = str(uuid.uuid4()), str(uuid.uuid4())
    try:
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO conversations (id,title,created_at,updated_at) VALUES (:id,'old',now(),now())"), {"id": c_id})
            connection.execute(text("INSERT INTO conversation_runs (id,conversation_id,status,request_id,created_at,updated_at) VALUES (:id,:c,'prepared','legacy-active',now(),now())"), {"id": run_id, "c": c_id})
        with pytest.raises(RuntimeError, match="Resolve legacy active runs"):
            command.upgrade(config, "head")
        with engine.connect() as connection:
            assert connection.execute(text("SELECT status FROM conversation_runs WHERE id=:id"), {"id": run_id}).scalar_one() == "prepared"
    finally:
        engine.dispose()
