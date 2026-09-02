# 前端路由模块，主要的前端交互路由接口，通过FastAPI进行实现
import logging
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent

from noteagent.chat.history import (
    ConversationRecord,
    conversation_title_from_question,
    start_turn,
) #对话的创建和获取titile
from noteagent.chat.schemas import (
    ConversationOut,
    MessageOut,
    RenameConversation,
    RequestModel,
    ReviewRequest,
)       #获取对应的路由请求体或者响应体的pydantic模型
from noteagent.web import read_home_html    #返回前端初始网页

_logger = logging.getLogger(__name__)
#APIRouter 本身不会直接接收请求，必须用 app.include_router(router) 挂载到主 app 才生效。
#方便进行模块拆分，如果直接@app.POST()直接挂载到应用上，不方便进行分模块化
router = APIRouter()

# 初始页面路由，加载主页面
@router.get("/", response_class=HTMLResponse)
async def home() -> str:
    """Serve the single-page chat UI."""
    return read_home_html()

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

#如果点击对应的对话，会触发此加载对应的聊天历史的消息
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
        record = history.rename(conversation_id, require.title)
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

# 普通的/chat路由，当用户在聊天框输入消息的时候，会激活此路由，然后添加进对应的会话历史消息中，并进行Agent的stream回复
@router.post("/chat", response_class=EventSourceResponse)
async def chat_with(
    request: Request,
    require: Annotated[RequestModel, Body()],
    record: Annotated[ConversationRecord, Depends(resolve_conversation)],
) -> AsyncIterator[ServerSentEvent]:
    """Persist user/assistant messages and stream chat tokens."""
    history = request.app.state.container.history
    turn_id = start_turn()
    history.append_message(record.id, "user", require.question, turn_id=turn_id)

    yield ServerSentEvent(
        event="conversation",
        data={"id": record.id, "title": record.title},
    )

    agent = request.app.state.container.chat_agent
    _logger.info("[conversation=%s] SSE request: %.80s", record.id, require.question)
    assistant_text = ""
    final_text: str | None = None
    async for item in agent.stream(require.question, thread_id=record.id, turn_id=turn_id):
        event = str(item.get("event") or "token")
        data = item.get("data")
        if data is None or data == "":
            continue
        if event == "token" and isinstance(data, str):
            assistant_text += data
        elif event == "assistant_final" and isinstance(data, str):
            final_text = data
            continue
        yield ServerSentEvent(event=event, data=data)

    persist = final_text if final_text is not None else assistant_text
    if persist:
        history.append_message(record.id, "assistant", persist, turn_id=turn_id)

# 
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
