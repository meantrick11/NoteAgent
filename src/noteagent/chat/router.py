# 前端路由模块，主要的前端交互路由接口，通过FastAPI进行实现
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.sse import EventSourceResponse, ServerSentEvent

from noteagent.chat.history import (
    conversation_title_from_question,
) #对话的创建和获取titile
from noteagent.chat.schemas import (
    CitationOut,
    ConversationDetailOut,
    ConversationOut,
    DraftContentRequest,
    MessageOut,
    RenameConversation,
    RequestModel,
    ReviewRequest,
    ToolStepOut,
)       #获取对应的路由请求体或者响应体的pydantic模型
from noteagent.conversations.contracts import (
    ConversationBusy,
    PreparedTurn,
    StaleConversation,
    TurnAlreadyClaimed,
)
from noteagent.model_management.router import (
    chat_lease,
    require_same_origin,
    write_lease,
)
from noteagent.model_management.service import RuntimeSnapshot

_logger = logging.getLogger(__name__)
#APIRouter 本身不会直接接收请求，必须用 app.include_router(router) 挂载到主 app 才生效。
#方便进行模块拆分，如果直接@app.POST()直接挂载到应用上，不方便进行分模块化
router = APIRouter()

#在初始路由之后，直接尝试加载对应的历史对话
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


# 消息可回退编辑需要持久化的安全边界；阶段 B 未完成前一律禁用并给出原因。
EDIT_RECOVERY_UNAVAILABLE = "recovery_not_available"
EDIT_NOT_MIGRATED = "history_not_migrated"


def _message_out(message) -> MessageOut:
    """Project one stored record into the HTTP contract, including editability."""
    reason = None
    if message.role == "user":
        reason = message.edit_unavailable_reason or EDIT_RECOVERY_UNAVAILABLE
    return MessageOut(
        id=message.id,
        role=message.role,
        content=message.content,
        created_at=message.created_at,
        turn_id=message.turn_id,
        citations=[CitationOut.model_validate(item) for item in (message.citations or [])],
        tool_steps=[ToolStepOut.model_validate(item) for item in (message.tool_steps or [])],
        editable=False,
        edit_unavailable_reason=reason,
    )


#如果点击对应的对话，会触发此加载对应的聊天历史的消息
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
    return [_message_out(m) for m in records]

# 更改路由，如果点击重命名会到此路由，进行对话的重命名路由操作
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

#前端删除模型的路由，如果点击删除对话，且“确定”之后，会路由到此，进行对应会话的历史的删除
@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: str, request: Request) -> None:
    """Delete a conversation and its messages (CASCADE). 404 if missing."""
    history = request.app.state.container.history
    try:
        await run_in_threadpool(history.delete, conversation_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="conversation not found")
    _logger.info("delete conversation=%s", conversation_id)


async def claim_turn(
    request: Request,
    require: Annotated[RequestModel, Body()],
    snapshot: Annotated[RuntimeSnapshot, Depends(chat_lease)],
) -> tuple[ConversationOut, PreparedTurn, bool]:
    """Resolve the conversation and durably accept the user message before SSE.

    Running as a dependency is what lets a duplicate request, a missing conversation,
    or a busy claim be answered with a real status code instead of a broken stream.
    The message is persisted here, so the browser's ``user_message`` event carries a
    server identity that already exists in the checkpoint. With ``run_id`` the turn is
    resumed instead: the accepted user message is not re-inserted.
    """
    container = request.app.state.container
    conversations = container.conversations
    if conversations is None:
        raise HTTPException(status_code=503, detail="conversation service unavailable")
    agent = snapshot.chat_agent

    if require.prepared_turn_id:
        return _claim_prepared_turn(conversations, require, agent)
    if require.run_id:
        return _claim_resume(conversations, require, agent)

    conv_id = require.conversation_id or require.thread_id
    if conv_id:
        record = conversations.get(conv_id)
        if record is None:
            raise HTTPException(status_code=404, detail="conversation not found")
        if record.state_backend != "checkpoint":
            raise HTTPException(
                status_code=409,
                detail="conversation history is not migrated to checkpoints yet",
            )
    else:
        record = await conversations.create_conversation(
            conversation_title_from_question(require.question)
        )

    request_id = require.request_id or uuid.uuid4().hex
    try:
        prepared = await agent.prepare(
            record.id,
            require.question,
            request_id,
            expected_revision=require.expected_revision,
        )
    except TurnAlreadyClaimed:
        raise HTTPException(status_code=409, detail="request already accepted")
    except ConversationBusy:
        raise HTTPException(status_code=409, detail="conversation has a running turn")
    except StaleConversation:
        raise HTTPException(status_code=409, detail="conversation revision changed")
    return (
        ConversationOut(id=record.id, title=record.title, updated_at=record.updated_at),
        prepared,
        False,
    )


def _claim_prepared_turn(
    conversations, require: RequestModel, agent
) -> tuple[ConversationOut, PreparedTurn, bool]:
    """Claim a recovery-forked prepared turn; the edited message is already accepted."""
    if require.question:
        raise HTTPException(
            status_code=422, detail="prepared_turn_id and question are mutually exclusive"
        )
    try:
        prepared = agent.claim_prepared(require.prepared_turn_id)
    except ConversationBusy:
        raise HTTPException(status_code=409, detail="conversation has a running turn")
    except TurnAlreadyClaimed:
        raise HTTPException(status_code=409, detail="turn already claimed")
    except StaleConversation:
        raise HTTPException(status_code=409, detail="conversation revision changed")
    except KeyError:
        raise HTTPException(status_code=404, detail="turn not found")
    record = conversations.get(prepared.conversation_id)
    if record is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return (
        ConversationOut(id=record.id, title=record.title, updated_at=record.updated_at),
        prepared,
        False,  # a freshly prepared turn runs from its accepted checkpoint, not resumed
    )


def _claim_resume(
    conversations, require: RequestModel, agent
) -> tuple[ConversationOut, PreparedTurn, bool]:
    """Claim an interrupted run for an explicit reconnect; never re-accept the user."""
    if require.question:
        raise HTTPException(
            status_code=422, detail="run_id and question are mutually exclusive"
        )
    try:
        prepared = agent.resume(
            require.run_id,
            conversation_id=require.conversation_id or require.thread_id,
            expected_revision=require.expected_revision,
        )
    except ConversationBusy:
        raise HTTPException(status_code=409, detail="conversation has a running turn")
    except TurnAlreadyClaimed:
        raise HTTPException(status_code=409, detail="run is not interrupted")
    except StaleConversation:
        raise HTTPException(status_code=409, detail="conversation revision changed")
    except KeyError:
        raise HTTPException(status_code=404, detail="run not found")
    requested = require.conversation_id or require.thread_id
    if requested and requested != prepared.conversation_id:
        raise HTTPException(status_code=404, detail="run not found")
    record = conversations.get(prepared.conversation_id)
    if record is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return (
        ConversationOut(id=record.id, title=record.title, updated_at=record.updated_at),
        prepared,
        True,
    )


# 普通的/chat路由，当用户在聊天框输入消息的时候，会激活此路由，然后添加进对应的会话历史消息中，并进行Agent的stream回复
@router.post("/chat", response_class=EventSourceResponse)
async def chat_with(
    request: Request,
    require: Annotated[RequestModel, Body()],
    claimed: Annotated[tuple[ConversationOut, PreparedTurn, bool], Depends(claim_turn)],
    snapshot: Annotated[RuntimeSnapshot, Depends(chat_lease)],
) -> AsyncIterator[ServerSentEvent]:
    """Run the graph turn for an already-claimed request and stream its events."""
    record, prepared, resume = claimed
    yield ServerSentEvent(
        event="conversation",
        data={"id": record.id, "title": record.title},
    )
    yield ServerSentEvent(
        event="user_message",
        data={
            "message_id": prepared.user_message_id,
            "turn_id": prepared.turn_id,
            "run_id": prepared.run_id,
            "request_id": prepared.request_id,
            "state_revision": prepared.generation,
        },
    )

    _logger.info(
        "[conversation=%s] SSE request resume=%s: %.80s",
        record.id,
        resume,
        require.question,
    )
    agent = snapshot.chat_agent
    async for item in agent.run(prepared, resume=resume):
        event = str(item.get("event") or "token")
        data = item.get("data")
        if data is None or data == "":
            continue
        if event == "assistant_final" and isinstance(data, str):
            # Browser gets the full text; assistant_final itself stays internal.
            yield ServerSentEvent(event="answer", data=data)
            continue
        yield ServerSentEvent(event=event, data=data)


@router.put("/chat/draft", dependencies=[Depends(require_same_origin)])
async def update_chat_draft(
    request: Request,
    require: Annotated[DraftContentRequest, Body()],
    snapshot: Annotated[RuntimeSnapshot, Depends(write_lease)],
) -> dict:
    """Save edits to the pending draft's body.

    Only the conversation's pending draft changes here: no note is written and no
    vector is touched. Approval still goes through POST /chat/review.
    """
    history = request.app.state.container.history
    if history.get(require.thread_id) is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    agent = snapshot.chat_agent
    _logger.info(
        "[thread=%s] draft update chars=%d", require.thread_id, len(require.content)
    )
    try:
        result = await agent.update_draft_content(
            require.thread_id,
            require.content,
            expected_revision=require.expected_revision,
        )
    except StaleConversation:
        raise HTTPException(status_code=409, detail="conversation revision changed")
    except ConversationBusy:
        raise HTTPException(status_code=409, detail="conversation has a running turn")
    if "error" in result:
        raise HTTPException(status_code=409, detail=result["error"])
    return _with_revision(request, require.thread_id, result)


def _with_revision(request: Request, conversation_id: str, payload: dict) -> dict:
    """Attach the fresh head revision so the client's next write token is current."""
    container = request.app.state.container
    record = container.history.get(conversation_id)
    if record is not None and record.state_backend == "checkpoint" and container.conversations:
        payload = {**payload, "state_revision": container.conversations.current_revision(conversation_id)}
    return payload


@router.post("/chat/review")
async def chat_review(
    request: Request,
    require: Annotated[ReviewRequest, Body()],
    snapshot: Annotated[RuntimeSnapshot, Depends(write_lease)],
) -> dict:
    """Apply or discard the pending note draft after human approval.

    Approval writes notes and reindexes them, so it is gated like any other write.
    """
    if request.app.state.container.history.get(require.thread_id) is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    agent = snapshot.chat_agent
    _logger.info(
        "[thread=%s] review action=%s write_action=%s file=%s",
        require.thread_id,
        require.action,
        require.write_action,
        require.file_name,
    )
    try:
        result = await agent.review(
            require.thread_id,
            require.action,
            write_action=require.write_action,
            file_name=require.file_name,
            expected_revision=require.expected_revision,
        )
    except StaleConversation:
        raise HTTPException(status_code=409, detail="conversation revision changed")
    except ConversationBusy:
        raise HTTPException(status_code=409, detail="conversation has a running turn")
    return _with_revision(request, require.thread_id, result)
