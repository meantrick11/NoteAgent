import logging
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent

from noteagent.chat.history import ConversationRecord, conversation_title_from_question
from noteagent.chat.schemas import (
    ConversationOut,
    MessageOut,
    RenameConversation,
    RequestModel,
    ReviewRequest,
)
from noteagent.web import read_home_html

_logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def home() -> str:
    """Serve the single-page chat UI."""
    return read_home_html()


@router.get("/conversations")
async def list_conversations(request: Request) -> list[ConversationOut]:
    """Return all chat conversations for the sidebar."""
    history = request.app.state.container.history
    records = history.list_conversations()
    _logger.info("list conversations count=%d", len(records))
    return [
        ConversationOut(id=r.id, title=r.title, updated_at=r.updated_at)
        for r in records
    ]


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(conversation_id: str, request: Request) -> list[MessageOut]:
    """Return the messages of one conversation, or 404 if missing."""
    history = request.app.state.container.history
    records = history.list_messages(conversation_id)
    if records is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    _logger.info("list messages conversation=%s count=%d", conversation_id, len(records))
    return [
        MessageOut(id=m.id, role=m.role, content=m.content, created_at=m.created_at)
        for m in records
    ]


@router.patch("/conversations/{conversation_id}")
async def rename_conversation(
    conversation_id: str,
    require: Annotated[RenameConversation, Body()],
    request: Request,
) -> ConversationOut:
    """Rename a conversation. 404 if missing; 400 if title empty or too long."""
    history = request.app.state.container.history
    try:
        record = history.rename(conversation_id, require.title)
    except KeyError:
        raise HTTPException(status_code=404, detail="conversation not found")
    except ValueError as exc:
        detail = "title is required" if "required" in str(exc) else "title too long"
        raise HTTPException(status_code=400, detail=detail)
    _logger.info("rename conversation=%s", conversation_id)
    return ConversationOut(id=record.id, title=record.title, updated_at=record.updated_at)


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: str, request: Request) -> None:
    """Delete a conversation and its messages (CASCADE). 404 if missing."""
    history = request.app.state.container.history
    try:
        history.delete(conversation_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="conversation not found")
    _logger.info("delete conversation=%s", conversation_id)


async def resolve_conversation(
    require: Annotated[RequestModel, Body()],
    request: Request,
) -> ConversationRecord:
    """Resolve or create the target conversation; 404 on an unknown id.

    Runs as a dependency so the 404 is raised before SSE streaming starts.
    """
    history = request.app.state.container.history
    conv_id = require.conversation_id or require.thread_id
    if conv_id:
        record = history.get(conv_id)
        if record is None:
            raise HTTPException(status_code=404, detail="conversation not found")
        return record
    return history.create(conversation_title_from_question(require.question))


@router.post("/chat", response_class=EventSourceResponse)
async def chat_with(
    request: Request,
    require: Annotated[RequestModel, Body()],
    record: Annotated[ConversationRecord, Depends(resolve_conversation)],
) -> AsyncIterator[ServerSentEvent]:
    """Persist user/assistant messages and stream chat tokens."""
    history = request.app.state.container.history
    history.append_message(record.id, "user", require.question)

    yield ServerSentEvent(
        event="conversation",
        data={"id": record.id, "title": record.title},
    )

    agent = request.app.state.container.chat_agent
    _logger.info("[conversation=%s] SSE request: %.80s", record.id, require.question)
    assistant_text = ""
    async for item in agent.stream(require.question, thread_id=record.id):
        event = str(item.get("event") or "token")
        data = item.get("data")
        if data is None or data == "":
            continue
        if event == "token" and isinstance(data, str):
            assistant_text += data
        yield ServerSentEvent(event=event, data=data)

    if assistant_text:
        history.append_message(record.id, "assistant", assistant_text)


@router.post("/chat/review")
async def chat_review(
    request: Request,
    require: Annotated[ReviewRequest, Body()],
) -> dict:
    """Apply or discard the pending note draft after human approval."""
    agent = request.app.state.container.chat_agent
    _logger.info(
        "[thread=%s] review action=%s write_action=%s file=%s",
        require.thread_id,
        require.action,
        require.write_action,
        require.file_name,
    )
    return agent.review(
        require.thread_id,
        require.action,
        write_action=require.write_action,
        file_name=require.file_name,
    )


@router.post("/chat/user_exit")
async def chat_user_exit(
    request: Request,
    require: Annotated[RequestModel, Body()],
) -> dict[str, str]:
    """Trigger session summarization when the user leaves the chat."""
    agent = request.app.state.container.chat_agent
    _logger.info("[thread=%s] User exit: summarizing session", require.thread_id)
    await agent.summarize_on_exit(require.thread_id)
    _logger.info("[thread=%s] User exit: finished", require.thread_id)
    return {"status": "finished"}
