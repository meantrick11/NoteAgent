"""Draft-mutation CAS defects found in the phase-A review.

S1: a draft edit must not move the head while a turn owns the conversation.
R1: a draft edit must be published against the head it was read from, so an
interleaved publish is rejected instead of silently overwritten.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage

from noteagent.conversations.checkpoints import checkpoint_id_of
from noteagent.conversations.contracts import ConversationBusy, StaleConversation
from support.fakes import FakeChatModel


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
