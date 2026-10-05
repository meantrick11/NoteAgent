"""PostgreSQL-backed checkpoint persistence: restart, pinning, and saver setup.

In-memory passing here does not prove persistence; these cases close and reopen
the saver and the SQLAlchemy engine against the same real schema.
"""

import pytest
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy import inspect

from NoteAgent.BusinessModules.ConversationState.ConversationCheckpoints import checkpoint_id_of, thread_config


async def test_state_and_head_survive_close_and_reopen(postgres_harness):
    h = postgres_harness
    assert h.is_persistent
    conversation = await h.create_conversation("persist")
    branch_id = h.service.active_branch_id(conversation.id)

    values = dict((await h.service.get_state(conversation.id)).values)
    values["ui_messages"] = [
        {"id": "u1", "role": "user", "content": "重启后仍在", "turn_id": None}
    ]
    values["run_status"] = "completed"
    await h.service.write_state(conversation.id, values, branch_id=branch_id, publish=True)
    head_before = h.active_head(conversation.id)

    await h.reopen()

    view = await h.service.get_state(conversation.id)
    assert view.values["ui_messages"][0]["content"] == "重启后仍在"
    assert view.values["run_status"] == "completed"
    assert view.config == head_before


async def test_older_checkpoint_is_still_readable_after_a_newer_write(postgres_harness):
    h = postgres_harness
    conversation = await h.create_conversation()
    first = await h.service.get_state(conversation.id)
    branch_id = h.service.active_branch_id(conversation.id)

    values = dict(first.values)
    values["ui_messages"] = [{"id": "u1", "role": "user", "content": "second"}]
    await h.service.write_state(conversation.id, values, branch_id=branch_id, publish=True)

    await h.reopen()

    pinned = await h.service.get_state(conversation.id, first.config)
    assert pinned.values["ui_messages"] == []
    assert checkpoint_id_of(pinned.config) == checkpoint_id_of(first.config)

    latest = await h.service.get_state(conversation.id)
    assert latest.values["ui_messages"][0]["content"] == "second"


async def test_saver_setup_created_its_own_tables(postgres_harness):
    """The checkpointer owns its tables; the app migration must not fake them."""
    h = postgres_harness
    await h.create_conversation()
    tables = set(inspect(h._engine).get_table_names())
    assert "checkpoints" in tables
    assert "checkpoint_writes" in tables
    # app-managed metadata lives in its own tables, created from Base.metadata
    assert {"conversations", "conversation_branches", "conversation_runs",
            "user_message_boundaries"} <= tables


async def test_two_conversations_do_not_share_checkpoint_state(postgres_harness):
    h = postgres_harness
    first = await h.create_conversation("a")
    second = await h.create_conversation("b")

    branch_id = h.service.active_branch_id(first.id)
    values = dict((await h.service.get_state(first.id)).values)
    values["ui_messages"] = [{"id": "u1", "role": "user", "content": "only-a"}]
    await h.service.write_state(first.id, values, branch_id=branch_id, publish=True)

    other = await h.service.get_state(second.id)
    assert other.values["ui_messages"] == []
    assert other.config != h.active_head(first.id)
