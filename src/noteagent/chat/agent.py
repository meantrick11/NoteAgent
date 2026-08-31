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
from noteagent.chat.drafts import (
    DraftStore,
    commit_review,
    current_thread_id,
    current_turn_id,
)
from noteagent.chat.history import ConversationStore
from noteagent.notes.repository import FileNoteRepository   #记笔记相关的功能函数类，比如read_file\write_file\create_file\delete_file等,用来记录笔记内容
from noteagent.observability.agent_trace import AgentTraceHandler   #Agent的跟踪器，用来记录Agent的运行轨迹

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
    ) -> None:
        self._model = model
        self._tools = tools
        self._notes = notes
        self._drafts = drafts
        self._history = history
        self._budget = budget
        self._summarize_dropped = summarize_dropped or self._default_summarize
        self._prompt_path = Path(__file__).resolve().parent / "prompts" / "system.txt"

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
        """Yield {event, data}: tokens and an optional draft. Writes tool stubs."""
        _logger.info(
            "agent stream start thread=%s turn=%s question=%.80s", thread_id, turn_id, question
        )
        token = current_thread_id.set(thread_id)
        token2 = current_turn_id.set(turn_id)
        try:
            runtime: list = []
            tool_map = {t.name: t for t in self._tools}
            tool_defs = "\n".join(f"{t.name}: {t.description}" for t in self._tools)
            system = self._prompt_path.read_text(encoding="utf-8")

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
            final_text = ""
            while True:
                pack = pack_now()   #初始化拼接输入（系统提示词、工具定义等等）
                run_compact_if_needed(pack)     #检查是否需要compact？如果需要，那么自动compact
                pack = pack_now(log=True)
                assembled_ai = None
                hop_tokens: list[str] = []
                async for chunk in bound.astream(
                    pack.messages, config={"callbacks": [AgentTraceHandler()]}
                ):
                    text = _chunk_text(chunk.content)   #全转换为String类型的文本
                    if text:
                        hop_tokens.append(text)
                    assembled_ai = chunk if assembled_ai is None else assembled_ai + chunk
                ai = assembled_ai
                if ai is None or not getattr(ai, "tool_calls", None):
                    final_text = "".join(hop_tokens)
                    for piece in hop_tokens:
                        yield {"event": "token", "data": piece}
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
                runtime.append(ai)
                for call in ai.tool_calls:
                    name = call["name"] if isinstance(call, dict) else getattr(call, "name")
                    args = (call.get("args") if isinstance(call, dict) else getattr(call, "args", None)) or {}
                    call_id = call["id"] if isinstance(call, dict) else getattr(call, "id")
                    try:
                        raw = await tool_map[name].ainvoke(args)
                        status = "ok"
                    except Exception as exc:
                        raw = {"error": str(exc)}
                        status = "error"
                    out = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
                    self._history.append_tool_stub(
                        thread_id, turn_id=turn_id, tool_name=name,
                        arguments=json.dumps(args, ensure_ascii=False),
                        output=out, status=status,
                        stub_preview_tokens=self._budget.stub_preview_tokens,
                        args_preview_chars=self._budget.args_preview_chars,
                    )
                    runtime.append(ToolMessage(content=out, tool_call_id=call_id, name=name))
            pending = self._drafts.get(thread_id)
            if pending is not None:
                yield {"event": "draft", "data": pending.as_dict()}
            _logger.info("agent stream end thread=%s turn=%s", thread_id, turn_id)
        finally:
            current_thread_id.reset(token)
            current_turn_id.reset(token2)

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
        )

    # 用户退出，由chat_user_exit路由激活使用
    async def summarize_on_exit(self, thread_id: str) -> None:
        """No-op. Log that context.md memory is disabled. Do not write notes/."""
        _logger.info("summarize_on_exit disabled thread=%s (context.md memory off)", thread_id)
