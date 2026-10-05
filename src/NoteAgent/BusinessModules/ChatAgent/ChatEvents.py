"""Translate model/tool activity into the existing SSE event contract.

Kept separate from the graph so the wire format has exactly one definition and the
browser-facing shapes do not depend on LangGraph internals.
"""

from __future__ import annotations

import json
from typing import Any

SSE_EVENT = dict[str, Any]


def chunk_text(content: object) -> str:
    """Turn LangChain message content into a displayable string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(str(block.get("text") or ""))
        return "".join(parts)
    return ""


def reasoning_text(chunk: object) -> str:
    """Optional model reasoning field; empty on ordinary chat models."""
    extra = getattr(chunk, "additional_kwargs", None) or {}
    if not isinstance(extra, dict):
        return ""
    for key in ("reasoning_content", "reasoning"):
        value = extra.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def has_tool_calls(message: object) -> bool:
    """True if this hop is (or is becoming) a tool call, not a user-visible reply."""
    return bool(getattr(message, "tool_calls", None) or getattr(message, "tool_call_chunks", None))


def tool_call_triple(call: object) -> tuple[str, str, dict]:
    """Return ``(id, name, args)`` for a LangChain tool_call dict or object."""
    if isinstance(call, dict):
        name = str(call.get("name") or "")
        call_id = str(call.get("id") or "")
        raw_args = call.get("args")
    else:
        name = str(getattr(call, "name", None) or "")
        call_id = str(getattr(call, "id", "") or "")
        raw_args = getattr(call, "args", None)
    return call_id or name, name, raw_args if isinstance(raw_args, dict) else {}


def named_tool_calls(message: object) -> list[tuple[str, str, dict]]:
    """Named tool_calls on this message (skip incomplete chunks without a name)."""
    found: list[tuple[str, str, dict]] = []
    seen: set[str] = set()
    for call in getattr(message, "tool_calls", None) or []:
        call_id, name, args = tool_call_triple(call)
        if not name or call_id in seen:
            continue
        seen.add(call_id)
        found.append((call_id, name, args))
    return found


def tool_call_id_of(call: object) -> str:
    """The id used to pair an AI tool call with its ToolMessage."""
    if isinstance(call, dict):
        return str(call.get("id") or call.get("name") or "")
    return str(getattr(call, "id", None) or getattr(call, "name", "") or "")


def thinking_event(*, after_tools: bool) -> SSE_EVENT:
    """Headline before a model call; a tool hop must not read as a fresh thought."""
    return {"event": "generating" if after_tools else "thinking", "data": "generating" if after_tools else "thinking"}


def hop_events(chunk: object, *, saw_tool: bool) -> list[SSE_EVENT]:
    """Token/think events for one streamed chunk.

    Once a hop has produced a tool call its prose and reasoning belong to the trace,
    never to the answer bubble.
    """
    events: list[SSE_EVENT] = []
    text = chunk_text(getattr(chunk, "content", ""))
    reason = reasoning_text(chunk)
    if saw_tool:
        for piece in (reason, text):
            if piece:
                events.append({"event": "think", "data": piece})
        return events
    if reason:
        events.append({"event": "think", "data": reason})
    if text:
        events.append({"event": "token", "data": text})
    return events


def tool_event(name: str, args: dict) -> SSE_EVENT:
    return {"event": "tool", "data": {"name": name, "args": args}}


def tool_done_event(name: str, status: str, preview: str, arguments: str) -> SSE_EVENT:
    return {
        "event": "tool_done",
        "data": {
            "name": name,
            "status": status,
            "preview": preview,
            "arguments": arguments,
        },
    }


def sources_event(sources: list[dict]) -> SSE_EVENT:
    return {"event": "sources", "data": sources}


def assistant_final_event(text: str) -> SSE_EVENT:
    """Internal final answer; the HTTP layer renames it to ``answer``."""
    return {"event": "assistant_final", "data": text}


def draft_event(payload: dict) -> SSE_EVENT:
    return {"event": "draft", "data": payload}


def error_event(message: str) -> SSE_EVENT:
    return {"event": "error", "data": message}


def json_args(args: dict) -> str:
    """Serialize tool arguments for storage and display."""
    return json.dumps(args, ensure_ascii=False)
