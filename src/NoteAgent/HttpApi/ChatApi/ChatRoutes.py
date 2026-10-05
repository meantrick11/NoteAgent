# 前端路由模块，主要的前端交互路由接口，通过FastAPI进行实现
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent

from NoteAgent.BusinessModules.ConversationState.LegacyConversationCompatibility.LegacyConversationStore import conversation_title_from_question
from NoteAgent.HttpApi.ConversationApi.ConversationSchemas import ConversationOut
from NoteAgent.HttpApi.ChatApi.ChatSchemas import DraftContentRequest, RequestModel, ReviewRequest
from NoteAgent.BusinessModules.ConversationState.ConversationContracts import ConversationBusy, PreparedTurn, StaleConversation, TurnAlreadyClaimed
from NoteAgent.HttpApi.RequestDependencies import chat_lease, require_same_origin, write_lease
from NoteAgent.ApplicationFlows.ModelRuntime.ModelRuntime import RuntimeSnapshot

_logger = logging.getLogger(__name__)
#APIRouter 本身不会直接接收请求，必须用 app.include_router(router) 挂载到主 app 才生效。
#方便进行模块拆分，如果直接@app.POST()直接挂载到应用上，不方便进行分模块化
router = APIRouter()

#在初始路由之后，直接尝试加载对应的历史对话




# 消息可回退编辑需要持久化的安全边界；阶段 B 未完成前一律禁用并给出原因。






#如果点击对应的对话，会触发此加载对应的聊天历史的消息

# 更改路由，如果点击重命名会到此路由，进行对话的重命名路由操作

#前端删除模型的路由，如果点击删除对话，且“确定”之后，会路由到此，进行对应会话的历史的删除


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
        prepared = agent.claim_prepared(require.prepared_turn_id,
            conversation_id=require.conversation_id or require.thread_id,
            expected_revision=require.expected_revision)
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
            "state_revision": request.app.state.container.conversations.current_revision(prepared.conversation_id),
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
    record = history.get(require.thread_id)
    if record is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    if request.app.state.container.history_required and record.state_backend != "checkpoint":
        raise HTTPException(status_code=409, detail="legacy conversation must be migrated before editing")
    agent = snapshot.chat_agent
    _logger.info(
        "[thread=%s] draft update chars=%d", require.thread_id, len(require.content)
    )
    try:
        result = await agent.update_draft_content(
            require.thread_id,
            require.content,
            expected_revision=require.expected_revision,
            **({"file_name": require.file_name} if require.file_name is not None else {}),
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
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
    record = request.app.state.container.history.get(require.thread_id)
    if record is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    if request.app.state.container.history_required and record.state_backend != "checkpoint":
        raise HTTPException(status_code=409, detail="legacy conversation must be migrated before reviewing")
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
