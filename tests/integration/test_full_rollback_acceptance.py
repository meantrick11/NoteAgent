"""End-to-end rollback acceptance over the real recovery stack.

Real notes on disk, a real shadow Git store and the real coordinator; only the
embedder/vector store are fakes (retrieval is the RecordingRetrieval-style double).
Covers the plan's G08 scenario and the neighbouring gates it can assert without a live
model.
"""

from __future__ import annotations

from sqlalchemy import select

from noteagent.notes.mutations import CREATE, WRITE, MutationCommand, Origin
from noteagent.recovery.models import IndexRepair
from noteagent.recovery.service import PlanConflict

from test_recovery_coordinator import _Env

import pytest


async def _owned_write(env, conversation_id, content, op):
    return env.mutations.apply(
        MutationCommand(kind=WRITE, file_name="A.md", content=content, append=False),
        Origin(kind="conversation", conversation_id=conversation_id), op,
        retrieval=env.retrieval,
    )


async def test_g08_rollback_updates_only_the_owned_file(tmp_path):
    env = _Env(tmp_path)
    # A.md exists before the boundary (created by another origin, before it).
    env.mutations.apply(
        MutationCommand(kind=CREATE, file_name="A.md", title="A", content="v1\n"),
        Origin.library(), "lib-init", retrieval=env.retrieval,
    )
    record, prepared = await env.turn("问题一")
    before_bytes = env.notes.path_of("A.md").read_bytes()
    env.mutations.apply(
        MutationCommand(kind=WRITE, file_name="A.md", content="v2-conversation\n", append=False),
        Origin(kind="conversation", conversation_id=record.id), "conv-write",
        retrieval=env.retrieval,
    )
    # Another session writes a different file afterwards.
    env.mutations.apply(
        MutationCommand(kind=CREATE, file_name="B.md", title="B", content="other session keeps this\n"),
        Origin.library(), "lib-b", retrieval=env.retrieval,
    )
    b_bytes = env.notes.path_of("B.md").read_bytes()

    preview_id, preview = await env.coordinator.preview(
        record.id, prepared.user_message_id, "modified question",
        expected_revision=env.conversations.get(record.id).revision,
    )
    assert preview.can_apply
    assert {change.path for change in preview.file_changes} == {"A.md"}

    job = await env.coordinator.start(
        preview_id, "modified question", ["A.md"], "accept-op-1"
    )
    assert job["status"] == "succeeded"

    assert env.notes.path_of("A.md").read_bytes() == before_bytes
    assert env.notes.path_of("B.md").read_bytes() == b_bytes

    with env.factory() as session:
        repairs = {
            row.path for row in session.scalars(
                select(IndexRepair).where(IndexRepair.operation_id == "accept-op-1:index")
            )
        }
    assert repairs == {"A.md"}
    assert env.repairs.is_synced("A.md", env.retrieval)

    state = await env.conversations.get_state(record.id)
    assert state.values["notes_commit"] == env.mutations.head_commit()
    users = [m for m in state.values["ui_messages"] if m["role"] == "user"]
    assert len(users) == 1 and users[0]["content"] == "modified question"


async def test_g11_state_only_recovery_makes_no_note_commit(tmp_path):
    env = _Env(tmp_path)
    record, prepared = await env.turn("问题一")
    commit_before = env.mutations.head_commit()

    preview_id, preview = await env.coordinator.preview(
        record.id, prepared.user_message_id, "改后的问题",
        expected_revision=env.conversations.get(record.id).revision,
    )
    assert preview.can_apply
    assert preview.requires_confirmation is False
    assert preview.file_changes == []

    job = await env.coordinator.start(preview_id, "改后的问题", [], "accept-op-2")
    assert job["status"] == "succeeded"
    assert env.mutations.head_commit() == commit_before  # no meaningless commit
    messages = await env.conversations.list_messages(record.id)
    assert messages[-1].content == "改后的问题"


async def test_g09_shared_change_blocks_the_whole_plan(tmp_path):
    env = _Env(tmp_path)
    env.mutations.apply(
        MutationCommand(kind=CREATE, file_name="A.md", title="A", content="v1\n"),
        Origin.library(), "lib-init", retrieval=env.retrieval,
    )
    record, prepared = await env.turn("问题一")
    await _owned_write(env, record.id, "conversation edit\n", "conv-write")
    # A different origin edits the same file after the boundary.
    env.mutations.apply(
        MutationCommand(kind=WRITE, file_name="A.md", content="someone else\n", append=False),
        Origin.library(), "lib-conflict", retrieval=env.retrieval,
    )
    disk_before = env.notes.path_of("A.md").read_bytes()

    preview_id, preview = await env.coordinator.preview(
        record.id, prepared.user_message_id, "改",
        expected_revision=env.conversations.get(record.id).revision,
    )
    assert not preview.can_apply and preview.conflicts
    with pytest.raises(PlanConflict):
        await env.coordinator.start(preview_id, "改", [], "accept-op-3")
    # Nothing was rolled back.
    assert env.notes.path_of("A.md").read_bytes() == disk_before


async def test_g13_repeat_start_returns_the_same_job(tmp_path):
    env = _Env(tmp_path)
    record, prepared = await env.turn("问题一")
    preview_id, preview = await env.coordinator.preview(
        record.id, prepared.user_message_id, "改后",
        expected_revision=env.conversations.get(record.id).revision,
    )
    first = await env.coordinator.start(preview_id, "改后", [], "accept-op-4")
    again = await env.coordinator.start(preview_id, "改后", [], "accept-op-4")
    assert first["job_id"] == again["job_id"]
