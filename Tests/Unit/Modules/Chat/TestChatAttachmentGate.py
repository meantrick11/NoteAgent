from types import SimpleNamespace
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI, HTTPException, Request

from NoteAgent.Modules.Sources.Service.SourceFileService import SourceFileError
from NoteAgent.Modules.Chat.Router.ChatRoutes import claim_turn
from NoteAgent.Modules.Chat.Domain.Dto.ChatSchemas import RequestModel
from NoteAgent.Modules.Conversations.Domain.Vo.ConversationRecords import MessageRecord, message_dict_from_record, record_from_ui
from NoteAgent.Modules.Conversations.Router.ConversationRoutes import _message_out


class Conversations:
    created = False

    async def create_conversation(self, title):
        self.created = True
        raise AssertionError("invalid attachment must not create conversation")


class Files:
    def ready_attachments(self, ids):
        raise SourceFileError("附件 ID 无效")


@pytest.mark.asyncio
async def test_invalid_attachment_is_rejected_before_new_conversation():
    app = FastAPI()
    conversations = Conversations()
    app.state.container = SimpleNamespace(conversations=conversations, source_files=Files())
    request = Request({"type": "http", "app": app})
    with pytest.raises(HTTPException) as error:
        await claim_turn(request, RequestModel(question="summarize", attachment_ids=["fake"]),
                         SimpleNamespace(chat_agent=object()))
    assert error.value.status_code == 400
    assert not conversations.created


@pytest.mark.asyncio
async def test_resume_cannot_attach_new_file():
    app = FastAPI()
    conversations = Conversations()
    app.state.container = SimpleNamespace(conversations=conversations, source_files=Files())
    request = Request({"type": "http", "app": app})
    with pytest.raises(HTTPException) as error:
        await claim_turn(request, RequestModel(run_id="run", attachment_ids=["fake"]),
                         SimpleNamespace(chat_agent=object()))
    assert error.value.status_code == 400
    assert not conversations.created


def test_checkpoint_attachment_roundtrip_and_deleted_projection():
    message = MessageRecord(
        id="message", conversation_id="conversation", role="user", content="question",
        created_at=datetime.now(timezone.utc), turn_id="turn", tool_name=None,
        tool_arguments=None, output_preview=None, truncated=False, status=None,
        attachments=[{"id": "file", "name": "lesson.txt", "parse_profile_revision": 2}],
    )
    restored = record_from_ui(message_dict_from_record(message))
    assert restored.attachments == message.attachments
    unavailable = SimpleNamespace(get=lambda _id: SimpleNamespace(status="deleted"))
    projected = _message_out(restored, source_files=unavailable)
    assert projected.attachments[0]["status"] == "deleted"
