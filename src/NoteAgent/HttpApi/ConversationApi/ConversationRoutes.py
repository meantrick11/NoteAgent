# 前端路由模块，主要的前端交互路由接口，通过FastAPI进行实现
import logging
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from NoteAgent.HttpApi.ConversationApi.ConversationSchemas import CitationOut, ConversationDetailOut, ConversationOut, MessageOut, RenameConversation, ToolStepOut

_logger = logging.getLogger(__name__)
#APIRouter 本身不会直接接收请求，必须用 app.include_router(router) 挂载到主 app 才生效。
#方便进行模块拆分，如果直接@app.POST()直接挂载到应用上，不方便进行分模块化
router = APIRouter()

#在初始路由之后，直接尝试加载对应的历史对话

EDIT_RECOVERY_UNAVAILABLE = "recovery_not_available"
EDIT_NOT_MIGRATED = "history_not_migrated"

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


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, request: Request) -> ConversationDetailOut:
    """Return one conversation and its pending draft, or 404 if missing.

    The pending draft is projected from the active checkpoint for migrated
    conversations, and from the legacy row until A1 imports them.
    """
    container = request.app.state.container
    record = container.history.get(conversation_id)
    if record is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    pending = record.pending_draft
    active_run = None
    recovery = None
    if record.state_backend == "checkpoint" and container.conversations is not None:
        pending = await container.conversations.get_pending_draft(conversation_id)
        active_run = container.conversations.get_active_run(conversation_id)
        recovery_coordinator = getattr(container, "recovery", None)
        if recovery_coordinator is not None:
            recovery = recovery_coordinator.get_for_conversation(conversation_id)
    _logger.info(
        "get conversation=%s backend=%s pending_draft=%s active_run=%s recovery=%s",
        conversation_id,
        record.state_backend,
        bool(pending),
        bool(active_run),
        bool(recovery),
    )
    return ConversationDetailOut(
        id=record.id,
        title=record.title,
        updated_at=record.updated_at,
        pending_draft=pending,
        state_revision=record.revision,
        active_run=active_run,
        recovery=recovery,
    )


def _message_out(message, editable=False) -> MessageOut:
    """Project one stored record into the HTTP contract, including editability."""
    reason = None
    if message.role == "user":
        reason = None if editable else message.edit_unavailable_reason or EDIT_RECOVERY_UNAVAILABLE
    return MessageOut(
        id=message.id,
        role=message.role,
        content=message.content,
        created_at=message.created_at,
        turn_id=message.turn_id,
        citations=[CitationOut.model_validate(item) for item in (message.citations or [])],
        tool_steps=[ToolStepOut.model_validate(item) for item in (message.tool_steps or [])],
        editable=editable,
        edit_unavailable_reason=reason,
    )


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(conversation_id: str, request: Request) -> list[MessageOut]:
    """Return the messages of one conversation, or 404 if missing."""
    container = request.app.state.container
    record = container.history.get(conversation_id)
    if record is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    if record.state_backend == "checkpoint" and container.conversations is not None:
        records = await container.conversations.list_messages(conversation_id)
    else:
        records = container.history.list_messages(conversation_id)
        for item in records or []:
            if item.role == "user":
                item.edit_unavailable_reason = EDIT_NOT_MIGRATED
    if records is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    _logger.info("list messages conversation=%s count=%d", conversation_id, len(records))
    editable_ids = set()
    if container.recovery is not None and container.conversations is not None:
        editable_ids = container.conversations.recoverable_message_ids(conversation_id)
    return [_message_out(m, m.role == "user" and m.id in editable_ids) for m in records]


@router.patch("/conversations/{conversation_id}")
async def rename_conversation(
    conversation_id: str,
    require: Annotated[RenameConversation, Body()],
    request: Request,
) -> ConversationOut:
    """Rename a conversation. 404 if missing; 400 if title empty or too long."""
    history = request.app.state.container.history
    try:
        record = await run_in_threadpool(history.rename, conversation_id, require.title)
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
        await run_in_threadpool(history.delete, conversation_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="conversation not found")
    _logger.info("delete conversation=%s", conversation_id)
