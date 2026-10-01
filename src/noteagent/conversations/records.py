"""Pure record types shared by the legacy store, the conversation service, and the graph.

Nothing here touches SQLAlchemy sessions, HTTP, or the checkpointer. ``GraphState``
is the persisted checkpoint schema, so it is defined here and imported by the chat
graph rather than the other way round.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, TypedDict

# Bump when a persisted GraphState changes shape in a way old data cannot satisfy.
STATE_SCHEMA_VERSION = 1

# Lifecycle markers for one prepared turn.
RUN_STATUSES = ("idle", "prepared", "running", "completed", "failed", "interrupted")


class GraphState(TypedDict, total=False):
    """The checkpointed state of one conversation branch."""

    schema_version: int
    # Complete user/assistant bubbles for display; compaction must never drop these.
    ui_messages: list[dict[str, Any]]
    # The model window: user/assistant records plus tool stubs, bounded by the watermark.
    working_records: list[dict[str, Any]]
    running_summary: str | None
    summary_watermark_turn_id: str | None
    pending_draft: dict[str, Any] | None
    # This turn's full AI tool calls and ToolMessages, paired by tool_call_id.
    runtime_messages: list[Any]
    citation_registry: list[dict[str, Any]]
    tool_steps: list[dict[str, Any]]
    current_turn_id: str | None
    current_user_id: str | None
    current_question: str | None
    tool_rounds: int
    branch_id: str | None
    generation: int
    notes_commit: str | None
    workspace_seq: int
    run_status: str


class StateSchemaError(ValueError):
    """Raised when a persisted state cannot be interpreted by this build."""


def initial_state(*, branch_id: str | None = None, generation: int = 0) -> GraphState:
    """A fresh terminal state: no messages, no pending work."""
    return GraphState(
        schema_version=STATE_SCHEMA_VERSION,
        ui_messages=[],
        working_records=[],
        running_summary=None,
        summary_watermark_turn_id=None,
        pending_draft=None,
        runtime_messages=[],
        citation_registry=[],
        tool_steps=[],
        current_turn_id=None,
        current_user_id=None,
        current_question=None,
        tool_rounds=0,
        branch_id=branch_id,
        generation=generation,
        notes_commit=None,
        workspace_seq=0,
        run_status="idle",
    )


def validate_state(values: Mapping[str, Any]) -> GraphState:
    """Return the state, or raise when its schema version is not understood."""
    version = values.get("schema_version")
    if version != STATE_SCHEMA_VERSION:
        raise StateSchemaError(f"unsupported state schema_version: {version!r}")
    return GraphState(**dict(values))


@dataclass(slots=True)
class ConversationRecord:
    """A conversation as shown in the sidebar."""

    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    running_summary: str | None
    summary_watermark_turn_id: str | None
    pending_draft: dict | None = None


@dataclass(slots=True)
class MessageRecord:
    """One user/assistant/tool row as stored or projected for display."""

    id: str
    conversation_id: str
    role: str
    content: str
    created_at: datetime
    turn_id: str | None
    tool_name: str | None
    tool_arguments: str | None
    output_preview: str | None
    truncated: bool
    status: str | None
    citations: list | None = None
    tool_steps: list | None = None


def ui_message_from_record(record: MessageRecord) -> dict[str, Any]:
    """Project a stored row into the checkpointed display record."""
    return {
        "id": record.id,
        "role": record.role,
        "content": record.content,
        "created_at": record.created_at.isoformat(),
        "turn_id": record.turn_id,
        "citations": list(record.citations or []),
        "tool_steps": list(record.tool_steps or []),
    }


def record_from_ui(item: Mapping[str, Any]) -> MessageRecord:
    """Rebuild a display record from checkpointed JSON."""
    created = item.get("created_at")
    return MessageRecord(
        id=str(item.get("id") or ""),
        conversation_id=str(item.get("conversation_id") or ""),
        role=str(item.get("role") or ""),
        content=str(item.get("content") or ""),
        created_at=(
            datetime.fromisoformat(created) if created else datetime.now(timezone.utc)
        ),
        turn_id=item.get("turn_id"),
        tool_name=item.get("tool_name"),
        tool_arguments=item.get("tool_arguments"),
        output_preview=item.get("output_preview"),
        truncated=bool(item.get("truncated")),
        status=item.get("status"),
        citations=list(item.get("citations") or []),
        tool_steps=list(item.get("tool_steps") or []),
    )
