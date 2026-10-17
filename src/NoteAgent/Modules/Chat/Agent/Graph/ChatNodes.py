"""Node implementations for the chat graph.

Every node takes the checkpointed state and returns only the keys it changed, so a
restart resumes from the last saved version and no node re-adds the user message.
"""

from __future__ import annotations

import logging
import asyncio
import inspect
from collections.abc import Callable, Awaitable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool
from langgraph.config import get_config, get_stream_writer

from NoteAgent.Modules.Chat.Domain.Vo import ChatEvents as events
from NoteAgent.Modules.Chat.Agent.Citations.CitationRegistry import CitationRegistry, current_citations, sanitize_answer
from NoteAgent.Modules.Chat.Agent.Tools.NoteSources import build_source_evidence, current_source_evidence
from NoteAgent.Modules.Chat.Agent.Context.ContextBudget import ContextBudget
from NoteAgent.Modules.Chat.Agent.Context.ContextCompaction import concat_summary, format_turns_for_summary, group_turns, select_turns_to_drop, should_compact
from NoteAgent.Modules.Chat.Agent.Context.ContextPack import PackResult, build_pack, draft_workspace_line
from NoteAgent.Modules.Chat.Agent.Context.TokenCounter import prefix_until_tokens
from NoteAgent.Modules.Conversations.Service.PendingDrafts import DraftStore, NoteDraft, DraftWorkspace, current_draft_workspace, current_thread_id as draft_thread_var, current_turn_id as draft_turn_var
from NoteAgent.Modules.Conversations.Domain.Vo.ConversationRecords import GraphState, MessageRecord, message_dict_from_record, record_from_ui
from NoteAgent.Modules.Sources.Service.SourceFileAccess import authorized_source_ids, read_source_ids

logger = logging.getLogger(__name__)


def graph_thread_id() -> str:
    """The conversation id for this run, taken from the graph config."""
    configurable = (get_config() or {}).get("configurable") or {}
    return str(configurable.get("thread_id") or "")


@dataclass
class GraphRuntime:
    """Dependencies every node needs; one instance per assembled agent."""

    model: BaseChatModel
    tools: list[BaseTool]
    drafts: DraftStore
    budget: ContextBudget
    system_prompt: str
    summarize_dropped: Callable[[str | None, str], str | Awaitable[str]]
    retrieval: object | None = None

    @property
    def tool_defs(self) -> str:
        return "\n".join(f"{tool.name}: {tool.description}" for tool in self.tools)

    @property
    def tool_map(self) -> dict[str, BaseTool]:
        return {tool.name: tool for tool in self.tools}


# ---- state projections ---------------------------------------------------


def records_from_state(state: GraphState) -> list[MessageRecord]:
    """Display records plus the tool stubs carried on assistant rows."""
    out: list[MessageRecord] = []
    for item in state.get("ui_messages") or []:
        record = record_from_ui(item)
        out.append(record)
        if record.role != "assistant":
            continue
        for index, step in enumerate(record.tool_steps or []):
            out.append(
                MessageRecord(
                    id=f"{record.id}:tool:{index}",
                    conversation_id=record.conversation_id,
                    role="tool",
                    content=str(step.get("preview") or ""),
                    created_at=record.created_at,
                    turn_id=record.turn_id,
                    tool_name=str(step.get("name") or ""),
                    tool_arguments=str(step.get("arguments") or ""),
                    output_preview=str(step.get("preview") or ""),
                    truncated=False,
                    status=str(step.get("status") or ""),
                )
            )
    return out


def after_watermark(
    records: list[MessageRecord], watermark: str | None
) -> list[MessageRecord]:
    """Records whose turn comes strictly after the watermark turn."""
    if watermark is None:
        return records
    groups: dict[Any, list[MessageRecord]] = {}
    order: list[Any] = []
    for record in records:
        key = record.turn_id if record.turn_id is not None else record.id
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(record)
    if watermark not in groups:
        return records
    kept: list[MessageRecord] = []
    for key in order[order.index(watermark) + 1 :]:
        kept.extend(groups[key])
    return kept


def window_records(state: GraphState) -> list[MessageRecord]:
    """The records the model window may see: everything after the watermark."""
    return after_watermark(records_from_state(state), state.get("summary_watermark_turn_id"))


def pending_draft_of(state: GraphState) -> NoteDraft | None:
    payload = state.get("pending_draft")
    return NoteDraft.from_dict(payload) if payload else None


def build_graph_pack(state: GraphState, runtime: GraphRuntime) -> PackResult:
    """Assemble the model input from checkpointed state (never from the DB)."""
    source_directory = []
    for item in state.get("ui_messages") or []:
        if item.get("role") == "user":
            source_directory.extend(item.get("attachments") or [])
    prompt = runtime.system_prompt
    if source_directory:
        directory = ", ".join(f"{item.get('name')} ({item.get('id')})" for item in source_directory)
        prompt += ("\n当前会话可按需读取以下用户附件来源：" + directory +
                   "。先用 list_source_files/read_source_file 工具按 ID 和定位读取，"+
                   "不得根据文件名猜测正文。仅用户要求生成笔记时提出草稿。")
    return build_pack(
        system_prompt=prompt,
        tool_defs=runtime.tool_defs,
        summary=state.get("running_summary"),
        persistent=window_records(state),
        current_turn_id=state.get("current_turn_id") or "",
        current_user=state.get("current_question") or "",
        draft_line=draft_workspace_line(pending_draft_of(state)),
        runtime_messages=list(state.get("runtime_messages") or []),
        budget=runtime.budget,
    )


# ---- nodes ---------------------------------------------------------------


async def compact_node(state: GraphState, runtime: GraphRuntime) -> dict[str, Any]:
    """Summarize the oldest complete turns until the pack fits the budget."""
    pack = build_graph_pack(state, runtime)
    if not should_compact(pack.pack_tokens, runtime.budget):
        return {}
    current_turn_id = state.get("current_turn_id") or ""
    drop, _keep = select_turns_to_drop(
        group_turns(window_records(state)),
        current_turn_id=current_turn_id,
        k_tokens=pack.k_tokens,
    )
    if not drop:
        logger.warning("compact skipped: no droppable complete turns")
        return {}
    last = drop[-1].turn_id
    if last == current_turn_id:
        logger.error("compact refused: watermark would be the current turn")
        return {}
    args = (state.get("running_summary"), format_turns_for_summary(drop))
    if inspect.iscoroutinefunction(runtime.summarize_dropped):
        chunk = await runtime.summarize_dropped(*args)
    else:
        # Compatibility for existing deterministic/sync summarizers; network
        # model.invoke must never block the application's event loop.
        chunk = await asyncio.to_thread(runtime.summarize_dropped, *args)
        if inspect.isawaitable(chunk):
            chunk = await chunk
    summary = concat_summary(state.get("running_summary"), chunk)
    remaining = after_watermark(records_from_state(state), last)
    logger.info(
        "compact dropped=%s summary_chars=%d working=%d",
        [bundle.turn_id for bundle in drop],
        len(summary),
        len(remaining),
    )
    return {
        "running_summary": summary,
        "summary_watermark_turn_id": last,
        "working_records": [message_dict_from_record(r) for r in remaining],
    }


async def model_node(state: GraphState, runtime: GraphRuntime) -> dict[str, Any]:
    """Stream one model hop, emitting SSE as it goes; record the assembled message."""
    writer = get_stream_writer()
    pack = build_graph_pack(state, runtime)
    runtime_messages = list(state.get("runtime_messages") or [])
    writer(events.thinking_event(after_tools=bool(runtime_messages)))

    bound = runtime.model.bind_tools(runtime.tools)
    assembled = None
    announced = set(state.get("announced_tool_ids") or [])
    saw_tool = False
    async for chunk in bound.astream(pack.messages):
        assembled = chunk if assembled is None else assembled + chunk
        if events.has_tool_calls(chunk) or events.has_tool_calls(assembled):
            saw_tool = True
        for call_id, name, args in events.named_tool_calls(assembled):
            if call_id in announced:
                continue
            announced.add(call_id)
            logger.info("tool announced tool=%s turn=%s", name, state.get("current_turn_id"))
            writer(events.tool_event(name, args))
        for event in events.hop_events(chunk, saw_tool=saw_tool):
            writer(event)

    if assembled is None:
        raise RuntimeError("model produced no output")
    logger.info(
        "model hop tool_calls=%s turn=%s", bool(assembled.tool_calls), state.get("current_turn_id")
    )
    return {
        "runtime_messages": runtime_messages + [assembled],
        "announced_tool_ids": sorted(announced),
    }


async def tools_node(state: GraphState, runtime: GraphRuntime) -> dict[str, Any]:
    """Execute this hop's tool calls and append their ToolMessages."""
    writer = get_stream_writer()
    runtime_messages = list(state.get("runtime_messages") or [])
    last = runtime_messages[-1] if runtime_messages else None
    calls = list(getattr(last, "tool_calls", None) or [])
    registry = CitationRegistry.from_list(state.get("citation_registry"))
    token = current_citations.set(registry)
    # The tools read the conversation identity from these vars; the checkpointed
    # state stays the source of truth, so they are set only for this call.
    token_thread = draft_thread_var.set(graph_thread_id())
    token_turn = draft_turn_var.set(str(state.get("current_turn_id") or ""))
    workspace = DraftWorkspace(graph_thread_id(), state.get("pending_draft"))
    token_draft = current_draft_workspace.set(workspace)
    allowed = {str(part.get("id")) for entry in (state.get("ui_messages") or [])
               if entry.get("role") == "user" for part in (entry.get("attachments") or [])}
    used = set()
    for steps in [*(entry.get("tool_steps") or [] for entry in state.get("ui_messages") or []), state.get("tool_steps") or []]:
        for step in steps:
            if step.get("name") == "read_source_file" and step.get("status") == "ok":
                try:
                    import json
                    used.add(str(json.loads(step.get("arguments") or "{}").get("source_id")))
                except (ValueError, TypeError):
                    pass
    token_allowed = authorized_source_ids.set(allowed)
    token_used = read_source_ids.set(used & allowed)
    steps = list(state.get("tool_steps") or [])
    # Source evidence for propose_note: what URLs the user gave, and how each read ended.
    user_texts = [state.get("current_question") or ""] + [
        r.content for r in records_from_state(state) if r.role == "user"
    ]
    tool_map = runtime.tool_map
    produced: list[ToolMessage] = []
    try:
        for call in calls:
            call_id, name, args = events.tool_call_triple(call)
            tool_call_id = events.tool_call_id_of(call)
            logger.info("tool start tool=%s turn=%s", name, state.get("current_turn_id"))
            web_status = None
            token_sources = None
            missing_source_selection = False
            if name == "propose_note":
                evidence = build_source_evidence(
                    user_texts, steps,
                    history=state.get("ui_messages") or [],
                    current_question=state.get("current_question") or "",
                )
                token_sources = current_source_evidence.set(evidence)
                missing_source_selection = bool(
                    args.get("action") != "delete"
                    and (evidence.fetched_ok or evidence.user_provided_after_failure)
                    and ("source_urls" not in args or "user_supplied_source_urls" not in args)
                )
            try:
                if missing_source_selection:
                    raw = {"error": "网页笔记必须明确传入 source_urls 和 user_supplied_source_urls；未采用网页时传空列表"}
                    status = "error"
                else:
                    raw = await tool_map[name].ainvoke(args)
                    status = "error" if isinstance(raw, dict) and "error" in raw else "ok"
            except Exception as exc:  # noqa: BLE001 - surfaced to the model and the trace
                raw = {"error": str(exc)}
                status = "error"
            finally:
                if token_sources is not None:
                    current_source_evidence.reset(token_sources)
            output = raw if isinstance(raw, str) else events.json_args(raw)
            if name == "read_webpage" and isinstance(raw, dict) and "status" in raw:
                # The step status reflects how much of the page was read; the raw value is
                # kept so draft sources can tell a successful fetch from a failed one.
                web_status = str(raw.get("status") or "")
                status = _web_step_status(web_status)
                preview, _truncated = _preview(_web_preview(raw), runtime.budget.stub_preview_tokens)
            else:
                preview, _truncated = _preview(output, runtime.budget.stub_preview_tokens)
            arguments = events.json_args(args)
            step: dict = {"name": name, "status": status, "preview": preview, "arguments": arguments}
            if web_status is not None:
                step["web_status"] = web_status
            steps.append(step)
            writer(events.tool_done_event(name, status, preview, arguments))
            produced.append(
                ToolMessage(content=output, tool_call_id=tool_call_id, name=name)
            )
    finally:
        current_citations.reset(token)
        draft_thread_var.reset(token_thread)
        draft_turn_var.reset(token_turn)
        current_draft_workspace.reset(token_draft)
        authorized_source_ids.reset(token_allowed)
        read_source_ids.reset(token_used)
    return {
        "runtime_messages": runtime_messages + produced,
        "tool_steps": steps,
        "citation_registry": registry.as_list(),
        "tool_rounds": int(state.get("tool_rounds") or 0) + 1,
        "pending_draft": workspace.payload,
    }


def _preview(text: str, stub_preview_tokens: int) -> tuple[str, bool]:
    """Display stub preview, mirroring the character budget of the legacy stub."""
    return prefix_until_tokens(text, stub_preview_tokens)


def _web_step_status(web_status: str) -> str:
    """Map a ``WebPageResult.status`` to the step status shown on the trace.

    A truncated read still counts as ``partial``; anything that did not yield the
    article body reads as ``error`` so it can never look like a successful fetch.
    """
    if web_status == "ok":
        return "ok"
    if web_status == "partial":
        return "partial"
    return "error"


def _web_preview(result: dict) -> str:
    """Short trace line for a webpage step: never the extracted body."""
    parts = [f"url={result.get('url') or ''}", f"status={result.get('status') or ''}"]
    if result.get("title"):
        parts.append(f"title={result['title']}")
    if result.get("error"):
        parts.append(f"error={result['error']}")
    return " ".join(parts)


async def finalize_node(state: GraphState, runtime: GraphRuntime) -> dict[str, Any]:
    """Write the assistant bubble, publish citations, and clear the turn runtime."""
    writer = get_stream_writer()
    runtime_messages = list(state.get("runtime_messages") or [])
    registry = CitationRegistry.from_list(state.get("citation_registry"))
    answer, used = _final_answer(runtime_messages, registry)
    writer(events.sources_event(used))

    draft = state.get("pending_draft")
    if draft is not None:
        writer(events.draft_event(draft))

    ui_messages = list(state.get("ui_messages") or [])
    turn_id = state.get("current_turn_id")
    added = False
    if answer:
        writer(events.assistant_final_event(answer))
        ui_messages.append(
            {
                "id": f"a-{turn_id}",
                "role": "assistant",
                "content": answer,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "turn_id": turn_id,
                "citations": used,
                "tool_steps": list(state.get("tool_steps") or []),
            }
        )
        added = True

    remaining = after_watermark(
        records_from_state({**state, "ui_messages": ui_messages}),
        state.get("summary_watermark_turn_id"),
    )
    logger.info(
        "finalize turn=%s answer_chars=%d citations=%d", turn_id, len(answer), len(used)
    )
    return {
        "ui_messages": ui_messages,
        "working_records": [message_dict_from_record(r) for r in remaining],
        "citation_registry": registry.as_list(),
        "pending_draft": draft,
        "runtime_messages": [],
        "tool_steps": [],
        "announced_tool_ids": [],
        "tool_rounds": 0,
        "run_status": "completed" if added else "failed",
    }


def _final_answer(
    runtime_messages: list, registry: CitationRegistry
) -> tuple[str, list[dict]]:
    """Sanitize the last assistant text that was not a tool call.

    Tool results never count: they carry content but are not the model's reply.
    """
    for message in reversed(runtime_messages):
        if isinstance(message, ToolMessage) or getattr(message, "tool_calls", None):
            continue
        text = events.chunk_text(getattr(message, "content", ""))
        if text.strip():
            return sanitize_answer(text, registry)
    return "", []


def route_after_model(state: GraphState) -> str:
    """Continue to tools while tool calls remain and the hop budget allows it."""
    runtime_messages = list(state.get("runtime_messages") or [])
    last = runtime_messages[-1] if runtime_messages else None
    if not getattr(last, "tool_calls", None):
        return "finalize"
    return "tools"


def route_after_tools(state: GraphState, budget: ContextBudget) -> str:
    """Stop calling tools once the hop budget is spent."""
    if int(state.get("tool_rounds") or 0) >= budget.max_tool_hops:
        logger.error("tool hop limit reached hops=%s", state.get("tool_rounds"))
        return "finalize"
    return "compact"
