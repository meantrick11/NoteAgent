"""Conversation metadata, explicit head reads, and state round-tripping."""

import uuid

import pytest

from NoteAgent.BusinessModules.ConversationState.ConversationCheckpoints import checkpoint_id_of, thread_config
from NoteAgent.BusinessModules.ConversationState.ConversationRecords import STATE_SCHEMA_VERSION, StateSchemaError, validate_state
from NoteAgent.BusinessModules.ConversationState.ConversationStateService import ConversationNotFound


async def test_create_conversation_starts_from_a_terminal_empty_state(
    conversation_harness,
):
    h = conversation_harness
    conversation = await h.create_conversation("first")

    view = await h.service.get_state(conversation.id)
    assert view.values["schema_version"] == STATE_SCHEMA_VERSION
    assert view.values["ui_messages"] == []
    assert view.values["working_records"] == []
    assert view.values["run_status"] == "idle"
    assert view.values["pending_draft"] is None
    assert view.values["branch_id"] == h.service.active_branch_id(conversation.id)
    assert checkpoint_id_of(view.config) is not None


async def test_active_head_is_not_the_savers_latest(conversation_harness):
    """A fork on the same thread must not become the state an app read returns."""
    h = conversation_harness
    conversation = await h.create_conversation()
    original = await h.service.get_state(conversation.id)

    # What the saver now considers "latest" is deliberately not the active head.
    abandoned = await h.fork_unpublished(conversation.id, original.config)
    latest = await h.runtime.saver.aget_tuple(thread_config(conversation.id))
    assert checkpoint_id_of(latest.config) == checkpoint_id_of(abandoned)

    shown = await h.service.get_state(conversation.id)
    assert shown.config == original.config
    assert shown.config != abandoned
    assert shown.values["ui_messages"] == []


async def test_pinned_read_returns_that_version_not_the_newest(conversation_harness):
    h = conversation_harness
    conversation = await h.create_conversation()
    first = await h.service.get_state(conversation.id)

    await h.fork_unpublished(conversation.id, first.config)

    pinned = await h.service.get_state(conversation.id, first.config)
    assert pinned.values["ui_messages"] == []
    assert checkpoint_id_of(pinned.config) == checkpoint_id_of(first.config)


async def test_state_values_round_trip_through_the_checkpointer(conversation_harness):
    h = conversation_harness
    conversation = await h.create_conversation()
    branch_id = h.service.active_branch_id(conversation.id)

    written = {
        "schema_version": STATE_SCHEMA_VERSION,
        "ui_messages": [{"id": "m1", "role": "user", "content": "你好\n第二行", "turn_id": None}],
        "working_records": [{"id": "m1", "role": "user", "content": "你好\n第二行"}],
        "running_summary": "摘要",
        "summary_watermark_turn_id": None,
        "pending_draft": {"action": "append", "file_name": "A.md", "content": "x"},
        "runtime_messages": [],
        "citation_registry": [],
        "tool_steps": [],
        "current_turn_id": None,
        "current_user_id": None,
        "current_question": None,
        "tool_rounds": 0,
        "branch_id": branch_id,
        "generation": 3,
        "notes_commit": None,
        "workspace_seq": 0,
        "run_status": "idle",
    }
    await h.service.write_state(conversation.id, written, branch_id=branch_id, publish=True)

    view = await h.service.get_state(conversation.id)
    assert view.values["ui_messages"] == written["ui_messages"]
    assert view.values["running_summary"] == "摘要"
    assert view.values["pending_draft"] == written["pending_draft"]
    assert view.values["generation"] == 3


async def test_list_messages_projects_the_active_checkpoint(conversation_harness):
    h = conversation_harness
    conversation = await h.create_conversation()
    assert await h.service.list_messages(conversation.id) == []

    branch_id = h.service.active_branch_id(conversation.id)
    values = dict((await h.service.get_state(conversation.id)).values)
    values["ui_messages"] = [
        {
            "id": "u1",
            "role": "user",
            "content": "保留换行\n第二行",
            "created_at": "2026-10-01T00:00:00+00:00",
            "turn_id": None,
            "citations": [],
            "tool_steps": [],
        }
    ]
    await h.service.write_state(conversation.id, values, branch_id=branch_id, publish=True)

    messages = await h.service.list_messages(conversation.id)
    assert [m.role for m in messages] == ["user"]
    assert messages[0].content == "保留换行\n第二行"


async def test_unknown_or_malformed_conversation_is_not_found(conversation_harness):
    h = conversation_harness
    with pytest.raises(ConversationNotFound):
        await h.service.get_state(str(uuid.uuid4()))
    with pytest.raises(ConversationNotFound):
        await h.service.get_state("not-a-uuid")
    assert await h.service.list_messages("not-a-uuid") is None


async def test_metadata_is_readable_from_the_legacy_store_view(conversation_harness):
    h = conversation_harness
    conversation = await h.create_conversation("标题")
    record = h.service.get(conversation.id)
    assert record is not None
    assert record.title == "标题"
    assert record.pending_draft is None


def test_unsupported_state_version_is_rejected():
    with pytest.raises(StateSchemaError, match="unsupported state schema_version"):
        validate_state({"schema_version": 999})
    with pytest.raises(StateSchemaError):
        validate_state({})


def test_records_module_stays_free_of_session_and_http():
    """The migrated DTOs must not drag a session or a web dependency along."""
    import NoteAgent.BusinessModules.ConversationState.ConversationRecords as records

    source = records.__doc__ or ""
    assert "checkpoint" in source
    assert not hasattr(records, "Session")
    assert not hasattr(records, "HTTPException")
