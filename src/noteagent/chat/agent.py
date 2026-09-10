import json
import logging  #日志记录
from collections.abc import AsyncIterator, Callable   #异步迭代器与回调类型
from pathlib import Path    #文件保存路径所用

from langchain_core.language_models.chat_models import BaseChatModel    #Agent的模型初始化所需的基础类
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import BaseTool   #工具基础类

from noteagent.chat.context_budget import ContextBudget
from noteagent.chat.context_compact import (
    format_turns_for_summary,
    group_turns,
    select_turns_to_drop,
    should_compact,
)
from noteagent.chat.context_pack import PackResult, build_pack, draft_workspace_line
from noteagent.chat.citations import (
    CitationRegistry,
    current_citations,
    sanitize_answer,
)
from noteagent.chat.drafts import (
    DraftStore,
    commit_review,
    current_thread_id,
    current_turn_id,
)
from noteagent.chat.history import ConversationStore
from noteagent.notes.repository import FileNoteRepository   #记笔记相关的功能函数类，比如read_file\write_file\create_file\delete_file等,用来记录笔记内容
from noteagent.observability.agent_trace import AgentTraceHandler   #Agent的跟踪器，用来记录Agent的运行轨迹
from noteagent.retrieval.service import RetrievalService

_logger = logging.getLogger(__name__)

# 从lagnchain的消息中将所有的内容：str/image 等数据全转换为string，或者""输出"
def _chunk_text(content: object) -> str:
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


def _has_tool_calls(message: object) -> bool:
    """True if this hop is (or is becoming) a tool call, not a user-visible reply."""
    calls = getattr(message, "tool_calls", None) or []
    chunks = getattr(message, "tool_call_chunks", None) or []
    return bool(calls) or bool(chunks)


def _tool_call_triple(call: object) -> tuple[str, str, dict]:
    """Return (id, name, args) for a LangChain tool_call dict or object."""
    if isinstance(call, dict):
        name = str(call.get("name") or "")
        call_id = str(call.get("id") or "")
        raw_args = call.get("args")
    else:
        name = str(getattr(call, "name", None) or "")
        call_id = str(getattr(call, "id", "") or "")
        raw_args = getattr(call, "args", None)
    args = raw_args if isinstance(raw_args, dict) else {}
    return call_id or name, name, args


def _reasoning_text(chunk: object) -> str:
    """Optional model reasoning field; empty on ordinary chat models."""
    extra = getattr(chunk, "additional_kwargs", None) or {}
    if not isinstance(extra, dict):
        return ""
    for key in ("reasoning_content", "reasoning"):
        val = extra.get(key)
        if isinstance(val, str) and val:
            return val
    return ""


def _named_tool_calls(message: object) -> list[tuple[str, str, dict]]:
    """Named tool_calls on this message (skip incomplete chunks without a name)."""
    found: list[tuple[str, str, dict]] = []
    seen: set[str] = set()
    for call in getattr(message, "tool_calls", None) or []:
        call_id, name, args = _tool_call_triple(call)
        if not name or call_id in seen:
            continue
        seen.add(call_id)
        found.append((call_id, name, args))
    return found


class ChatAgent:
    """Streams chat tokens and pending drafts; writes notes only after review."""   #流式输出聊天内容和待处理的草稿; 只有在审核通过后才写入笔记

    def __init__(
        self,
        model: BaseChatModel,
        tools: list[BaseTool],
        notes: FileNoteRepository,
        drafts: DraftStore,
        history: ConversationStore,
        budget: ContextBudget,
        summarize_dropped: Callable[[str | None, str], str] | None = None,
        retrieval: RetrievalService | None = None,
        prompt_path: Path | None = None,
    ) -> None:
        self._model = model
        self._tools = tools
        self._notes = notes
        self._drafts = drafts
        self._history = history
        self._budget = budget
        self._summarize_dropped = summarize_dropped or self._default_summarize
        self._retrieval = retrieval
        self._prompt_path = prompt_path or Path(__file__).resolve().parent / "prompts" / "system.txt"

    def _default_summarize(self, old: str | None, dropped: str) -> str:
        """Summarize only the dropped turns into a fresh chunk; never rewrite old."""
        prompt = (
            "下面「已有摘要」不要改写。"
            "只摘要「移出窗口的对话」，保住用户任务目标。"
            "只输出新摘要段落。\n\n"
            f"已有摘要：\n{old or '（空）'}\n\n移出的对话：\n{dropped}"
        )
        return _chunk_text(self._model.invoke([HumanMessage(content=prompt)]).content)

    async def stream(
        self, question: str, thread_id: str, turn_id: str
    ) -> AsyncIterator[dict]:
        """Yield thinking, tool, token, sources, and optional draft events."""
        _logger.info(
            "agent stream start thread=%s turn=%s question=%.80s", thread_id, turn_id, question
        )
        token = current_thread_id.set(thread_id)
        token2 = current_turn_id.set(turn_id)
        registry = CitationRegistry()
        token3 = current_citations.set(registry)
        try:    #为了定义pack&compact相关的函数
            runtime: list = []
            tool_map = {t.name: t for t in self._tools} #将工具名和工具对象映射到字典中tool_name->tool_function
            tool_defs = "\n".join(f"{t.name}: {t.description}" for t in self._tools)    #将工具的定义描述打包为字符串，方便发送给LLM（此处是为了构建对应的提示词）
            system = self._prompt_path.read_text(encoding="utf-8")  #获取系统提示词

            def pack_now(*, log: bool = False) -> PackResult:
                conv = self._history.get(thread_id)
                summary = conv.running_summary if conv else None
                pack = build_pack(
                    system_prompt=system,
                    tool_defs=tool_defs,
                    summary=summary,
                    persistent=self._history.list_persistent_after_watermark(thread_id),
                    current_turn_id=turn_id,
                    current_user=question,
                    draft_line=draft_workspace_line(self._drafts.get(thread_id)),
                    runtime_messages=runtime,
                    budget=self._budget,
                )
                if log:
                    _logger.info(
                        "context pack conversation=%s turn=%s has_summary=%s "
                        "runtime_msgs=%d pack_tokens=%d F=%d K=%d trigger=%d",
                        thread_id,
                        turn_id,
                        bool(summary and summary.strip()),
                        len(runtime),
                        pack.pack_tokens,
                        pack.f_tokens,
                        pack.k_tokens,
                        self._budget.trigger_tokens(),
                    )
                return pack

            def run_compact_if_needed(pack: PackResult) -> None:
                if not should_compact(pack.pack_tokens, self._budget):
                    return
                _logger.info(
                    "compact trigger conversation=%s turn=%s pack_tokens=%d trigger=%d F=%d K=%d",
                    thread_id,
                    turn_id,
                    pack.pack_tokens,
                    self._budget.trigger_tokens(),
                    pack.f_tokens,
                    pack.k_tokens,
                )
                drop, _keep = select_turns_to_drop(
                    group_turns(self._history.list_persistent_after_watermark(thread_id)),
                    current_turn_id=turn_id,
                    k_tokens=pack.k_tokens,
                )
                if not drop:
                    _logger.warning(
                        "compact skipped conversation=%s no droppable complete turns", thread_id
                    )
                    return
                conv = self._history.get(thread_id)
                chunk = self._summarize_dropped(
                    conv.running_summary if conv else None,
                    format_turns_for_summary(drop),
                )
                last = drop[-1].turn_id
                if last == turn_id:
                    _logger.error(
                        "compact refused watermark=current turn conversation=%s", thread_id
                    )
                    return
                self._history.apply_compact(
                    thread_id, summary_append=chunk, watermark_turn_id=last
                )
                _logger.info(
                    "compact conversation=%s dropped=%s F=%s K=%s pack=%s",
                    thread_id, [b.turn_id for b in drop], pack.f_tokens, pack.k_tokens, pack.pack_tokens,
                )

            bound = self._model.bind_tools(self._tools) #将工具绑定到LLM上
            tool_rounds = 0
            used_tools = False
            while True:
                pack = pack_now()   #初始化拼接输入（系统提示词、工具定义等等）
                run_compact_if_needed(pack)     #检查是否需要compact？如果需要，那么自动compact
                pack = pack_now(log=True)   #再次打包拼接提示词，如果有compact则是新的内容，如果没有，则是旧内容
                # After tools, generating must not look like a fresh "thinking" headline.
                if used_tools:
                    yield {"event": "generating", "data": "generating"}
                else:
                    yield {"event": "thinking", "data": "thinking"}
                assembled_ai = None
                hop_tokens: list[str] = []
                saw_tool = False
                announced_ids: set[str] = set()
                async for chunk in bound.astream(
                    pack.messages, config={"callbacks": [AgentTraceHandler()]}
                ):
                    assembled_ai = chunk if assembled_ai is None else assembled_ai + chunk
                    if _has_tool_calls(chunk) or _has_tool_calls(assembled_ai):
                        saw_tool = True
                    for call_id, name, args in _named_tool_calls(assembled_ai):
                        if call_id in announced_ids:
                            continue
                        announced_ids.add(call_id)
                        _logger.info(
                            "tool announced conversation=%s turn=%s tool=%s",
                            thread_id, turn_id, name,
                        )
                        yield {"event": "tool", "data": {"name": name, "args": args}}
                    text = _chunk_text(chunk.content)
                    reason = _reasoning_text(chunk)
                    # Tool hops: prose/reasoning go to the trace, never the bubble.
                    if saw_tool:
                        for piece in (reason, text):
                            if piece:
                                yield {"event": "think", "data": piece}
                    else:
                        if reason:
                            yield {"event": "think", "data": reason}
                        if text:
                            hop_tokens.append(text)
                            yield {"event": "token", "data": text}
                ai = assembled_ai
                if ai is None or not getattr(ai, "tool_calls", None):
                    final_text = "".join(hop_tokens)
                    final_text, used = sanitize_answer(final_text, registry)
                    yield {"event": "sources", "data": used}
                    if final_text:
                        yield {"event": "assistant_final", "data": final_text}
                    break
                if tool_rounds >= self._budget.max_tool_hops:
                    _logger.error(
                        "tool hop limit conversation=%s turn=%s hops=%s",
                        thread_id, turn_id, self._budget.max_tool_hops,
                    )
                    break
                tool_rounds += 1
                used_tools = True
                runtime.append(ai)
                for call in ai.tool_calls:
                    call_id, name, args = _tool_call_triple(call)
                    if isinstance(call, dict):
                        tool_call_id = call.get("id") or call_id
                    else:
                        tool_call_id = getattr(call, "id", None) or call_id
                    if call_id not in announced_ids:
                        announced_ids.add(call_id)
                        yield {"event": "tool", "data": {"name": name, "args": args}}
                    _logger.info("tool start conversation=%s turn=%s tool=%s", thread_id, turn_id, name)
                    try:
                        raw = await tool_map[name].ainvoke(args)
                        status = "ok"
                    except Exception as exc:
                        raw = {"error": str(exc)}
                        status = "error"
                    out = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
                    stub = self._history.append_tool_stub(
                        thread_id, turn_id=turn_id, tool_name=name,
                        arguments=json.dumps(args, ensure_ascii=False),
                        output=out, status=status,
                        stub_preview_tokens=self._budget.stub_preview_tokens,
                        args_preview_chars=self._budget.args_preview_chars,
                    )
                    yield {
                        "event": "tool_done",
                        "data": {
                            "name": name,
                            "status": status,
                            "preview": stub.output_preview or "",
                            "arguments": stub.tool_arguments or "",
                        },
                    }
                    runtime.append(ToolMessage(content=out, tool_call_id=tool_call_id, name=name))
            pending = self._drafts.get(thread_id)
            if pending is not None:
                yield {"event": "draft", "data": pending.as_dict()}
            _logger.info("agent stream end thread=%s turn=%s", thread_id, turn_id)
        finally:
            current_thread_id.reset(token)
            current_turn_id.reset(token2)
            current_citations.reset(token3)

    #用户检查的函数
    def review(
        self,
        thread_id: str,
        action: str,
        write_action: str | None = None,
        file_name: str | None = None,
    ) -> dict:
        """Approve, override, or reject the pending draft for this thread."""
        return commit_review(
            self._notes,
            self._drafts,
            thread_id,
            action,
            write_action=write_action,
            file_name=file_name,
            retrieval=self._retrieval,
        )
