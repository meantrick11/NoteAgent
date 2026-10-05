
from pydantic import BaseModel, field_validator

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
    """Edited draft body and optional target name; never a note write."""

    thread_id: str
    content: str
    file_name: str | None = None
    expected_revision: int | None = None

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, value: str) -> str:
        """Reject an empty body before it reaches the store's write validation."""
        if not value.strip():
            raise ValueError("content is required")
        return value
