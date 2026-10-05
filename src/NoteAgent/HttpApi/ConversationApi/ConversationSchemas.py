from datetime import datetime
from pydantic import BaseModel, Field

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
