from datetime import datetime

from pydantic import BaseModel, Field

#/chat 路由的请求体模型
class RequestModel(BaseModel):
    """JSON body for /chat."""

    question: str
    conversation_id: str | None = None
    thread_id: str | None = None

# 
class ReviewRequest(BaseModel):
    """JSON body for /chat/review."""

    thread_id: str
    action: str
    write_action: str | None = None
    file_name: str | None = None


class ConversationOut(BaseModel):
    """Conversation summary returned by GET /conversations."""

    id: str
    title: str
    updated_at: datetime


class ConversationDetailOut(ConversationOut):
    """One conversation plus the current pending draft, if any."""

    pending_draft: dict | None = None


class CitationOut(BaseModel):
    """One citation mapping stored on an assistant message."""

    index: int
    file_name: str
    chunk_index: int | None = None
    quote: str | None = None


class ToolStepOut(BaseModel):
    """Truncated tool stub attached to an assistant bubble (not a chat row)."""

    name: str
    status: str = ""
    preview: str = ""
    arguments: str = ""


class MessageOut(BaseModel):
    """One message bubble returned by GET /conversations/{id}/messages."""

    id: str
    role: str
    content: str
    created_at: datetime
    citations: list[CitationOut] = Field(default_factory=list)
    tool_steps: list[ToolStepOut] = Field(default_factory=list)


class RenameConversation(BaseModel):
    """JSON body for PATCH /conversations/{id}."""

    title: str
