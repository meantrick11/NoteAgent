from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from NoteAgent.ApplicationFlows.ConversationRecovery.RecoveryCoordinator import RecoveryCoordinator
from NoteAgent.BusinessModules.ConversationState.ConversationRecords import MessageRecord


@pytest.mark.asyncio
async def test_editing_history_keeps_original_attachment_references():
    message = MessageRecord(
        id="message", conversation_id="conversation", role="user", content="old",
        created_at=datetime.now(timezone.utc), turn_id="turn", tool_name=None,
        tool_arguments=None, output_preview=None, truncated=False, status=None,
        attachments=[{"id": "file", "name": "lesson.txt", "parse_profile_revision": 2}],
    )
    captured = {}

    async def state():
        return SimpleNamespace(values={"ui_messages": [], "working_records": []})

    async def fork(_conversation_id, _before, values, **_kwargs):
        captured.update(values)
        return SimpleNamespace(branch_id="branch", run_id="run",
                               config={"configurable": {"checkpoint_id": "checkpoint"}})

    service = SimpleNamespace(get_state=lambda *_args: state(),
        list_messages=lambda *_args: list_messages(), fork_for_edit=fork)

    async def list_messages():
        return [message]

    coordinator = RecoveryCoordinator.__new__(RecoveryCoordinator)
    coordinator._conversations = service
    coordinator._gate = SimpleNamespace(state=lambda: SimpleNamespace(seq=1))
    coordinator._boundary_row = lambda _id: {"before_checkpoint_id": "before"}
    await coordinator._prepare_state("conversation", "message", "new", "operation", {"commit": "head"})
    assert captured["ui_messages"][-1]["attachments"] == message.attachments
