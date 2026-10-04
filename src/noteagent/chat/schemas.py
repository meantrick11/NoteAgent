from datetime import datetime

from pydantic import BaseModel, Field, field_validator

#/chat 路由的请求体模型
class RequestModel(BaseModel):
    """JSON body for /chat."""

    question: str = ""
    conversation_id: str | None = None
    thread_id: str | None = None
    # Client-supplied idempotency key; a duplicate is accepted at most once.
    request_id: str | None = None
    # Explicit resume of an interrupted run; mutually exclusive with a new question.
    run_id: str | None = None
    # A recovery-forked prepared turn: claims the accepted message, never re-prepares.
    prepared_turn_id: str | None = None
    # Optional guard: refuse the turn when the conversation revision has moved on.
    expected_revision: int | None = None

# 
class ReviewRequest(BaseModel):
    """JSON body for /chat/review."""

    thread_id: str
    action: str
    write_action: str | None = None
    file_name: str | None = None
    expected_revision: int | None = None


class DraftContentRequest(BaseModel):
    """JSON body for PUT /chat/draft: the edited body of the pending draft only."""

    thread_id: str
    content: str
    expected_revision: int | None = None

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, value: str) -> str:
        """Reject an empty body before it reaches the store's write validation."""
        if not value.strip():
            raise ValueError("content is required")
        return value


class ConversationOut(BaseModel):
    """Conversation summary returned by GET /conversations."""

    id: str
    title: str
    updated_at: datetime


class ConversationDetailOut(ConversationOut):
    """One conversation plus the current pending draft, if any."""

    pending_draft: dict | None = None
    # Monotonic head revision; the value draft saves/approvals must send back so a
    # stale tab is refused instead of overwriting newer state.
    state_revision: int = 0
    # The prepared/running/interrupted run, so a reconnect can resume the exact run.
    active_run: dict | None = None
    # An in-flight or failed recovery job, so the client can show progress/continue.
    recovery: dict | None = None


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
    turn_id: str | None = None
    citations: list[CitationOut] = Field(default_factory=list)
    tool_steps: list[ToolStepOut] = Field(default_factory=list)
    # Editable only when a recoverable boundary exists; until phase B lands this is
    # always false and edit_unavailable_reason explains why.
    editable: bool = False
    edit_unavailable_reason: str | None = None


class RenameConversation(BaseModel):
    """JSON body for PATCH /conversations/{id}."""

    title: str
