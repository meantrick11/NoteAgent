import logging  #日志记录
from collections.abc import AsyncIterator   #异步迭代器
from pathlib import Path    #文件保存路径所用

from langchain.agents import create_agent   #上层快速搭建Agent所用
from langchain.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage   #langchain对Messges的封装
from langchain_core.language_models.chat_models import BaseChatModel    #Agent的模型初始化所需的基础类
from langchain_core.tools import BaseTool   #工具基础类
from langgraph.checkpoint.memory import InMemorySaver   #langchain的上层临时记忆

from noteagent.chat.drafts import DraftStore, commit_review, current_thread_id
from noteagent.notes.repository import FileNoteRepository   #记笔记相关的功能函数类，比如read_file\write_file\create_file\delete_file等,用来记录笔记内容
from noteagent.observability.agent_trace import AgentTraceHandler   #Agent的跟踪器，用来记录Agent的运行轨迹

_logger = logging.getLogger(__name__)


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
    ):
        self._notes = notes
        self._drafts = drafts
        self._prompt_path = Path(__file__).resolve().parent / "prompts" / "system.txt"
        self._agent = create_agent(
            model=model,
            tools=tools,
            checkpointer=InMemorySaver(),
        )

    def _run_config(self, thread_id: str) -> dict:
        """LangGraph config: thread checkpoint key plus LLM/tool tracing."""
        return {
            "configurable": {"thread_id": thread_id},
            "callbacks": [AgentTraceHandler()],
        }

    def _system_prompt(self) -> SystemMessage:
        """Load the versioned system prompt from chat/prompts/system.txt."""
        content = self._prompt_path.read_text(encoding="utf-8")
        return SystemMessage(content=content)

    def _opening_messages(self, question: str) -> list:
        """First-turn messages: system prompt, optional context.md, user question."""
        human = HumanMessage(content=question)
        system = self._system_prompt()
        try:
            context = self._notes.read("context.md")
            return [system, SystemMessage(content=context), human]
        except FileNotFoundError:
            return [system, human]

    async def stream(self, question: str, thread_id: str) -> AsyncIterator[dict]:
        """Yield {event, data} items: token strings and an optional draft payload."""
        _logger.info("agent stream start thread=%s question=%.80s", thread_id, question)
        token = current_thread_id.set(thread_id)
        try:
            config = self._run_config(thread_id)
            state = await self._agent.aget_state(config=config)
            if state.values:
                messages = [HumanMessage(content=question)]
            else:
                messages = self._opening_messages(question)

            chars = 0
            async for _mode, chunk in self._agent.astream(
                input={"messages": messages},
                config=config,
                stream_mode=["messages"],
            ):
                ai_message, _metadata = chunk
                if isinstance(ai_message, (AIMessage, AIMessageChunk)):
                    text = _chunk_text(ai_message.content)
                    if text:
                        chars += len(text)
                        yield {"event": "token", "data": text}

            pending = self._drafts.get(thread_id)
            if pending is not None:
                yield {"event": "draft", "data": pending.as_dict()}
            _logger.info("agent stream end thread=%s chars=%d", thread_id, chars)
        finally:
            current_thread_id.reset(token)

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

    async def summarize_on_exit(self, thread_id: str) -> None:
        """Append a short session-end line to context.md without HITL."""
        _logger.info("agent summarize start thread=%s", thread_id)
        try:
            self._notes.read("context.md")
        except FileNotFoundError:
            self._notes.create("context.md", "学习上下文")
        self._notes.write(
            "context.md",
            f"\n## 本次对话\n- 会话结束 thread={thread_id}\n\n",
            append=True,
        )
        _logger.info("agent summarize end thread=%s", thread_id)
