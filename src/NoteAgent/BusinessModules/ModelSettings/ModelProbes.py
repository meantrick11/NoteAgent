"""Connection probes: verify streaming and actual tool calls without saving configuration."""

from __future__ import annotations
import asyncio
from dataclasses import dataclass
from langchain.tools import tool
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from NoteAgent.BusinessModules.ModelSettings.ModelErrors import ModelProbeTimeoutError, _probe_error

PROBE_TIMEOUT_SECONDS = 20.0

@dataclass(frozen=True)
class ChatProbeResult:
    """What a connection test observed about one candidate."""

    streaming: bool
    tool_calling: bool
    message: str | None = None

    @property
    def verified(self) -> bool:
        """A candidate is only usable when both capabilities work."""
        return self.streaming and self.tool_calling


@tool("probe_tool", description="回显传入的 value，用于验证工具调用协议。")
def _probe_tool(value: str) -> str:
    """Echo the probe value back to the model."""
    return value


def _chunk_text(content: object) -> str:
    """Displayable text of a streamed chunk's content."""
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


def _describe_probe(result: ChatProbeResult) -> str:
    """Explain which capability a candidate lacks."""
    missing: list[str] = []
    if not result.streaming:
        missing.append("流式输出")
    if not result.tool_calling:
        missing.append("工具调用")
    if not missing:
        return "模型未通过验证"
    return f"模型未通过验证：不支持 {'、'.join(missing)}，无法作为聊天模型使用"


async def probe_streaming(model: BaseChatModel) -> bool:
    """Request 1/2: a short prompt must stream at least one text chunk."""
    try:
        async with asyncio.timeout(PROBE_TIMEOUT_SECONDS):
            async for chunk in model.astream(
                [HumanMessage(content="只回复两个字：你好")]
            ):
                if _chunk_text(chunk.content):
                    return True
    except TimeoutError as exc:
        raise ModelProbeTimeoutError("模型服务响应超时（20 秒内没有回复）") from exc
    except Exception as exc:
        raise _probe_error(exc) from exc
    return False


async def probe_tool_calling(model: BaseChatModel) -> bool:
    """Request 2/2: a bound probe tool must actually be called."""
    bound = model.bind_tools([_probe_tool])
    try:
        async with asyncio.timeout(PROBE_TIMEOUT_SECONDS):
            async for chunk in bound.astream(
                [HumanMessage(content="请调用 probe_tool，value 传 ping。不要输出解释。")]
            ):
                if getattr(chunk, "tool_calls", None) or getattr(
                    chunk, "tool_call_chunks", None
                ):
                    return True
    except TimeoutError as exc:
        raise ModelProbeTimeoutError("工具调用验证超时（20 秒内没有回复）") from exc
    except Exception as exc:
        raise _probe_error(exc) from exc
    return False


async def probe_model(model: BaseChatModel) -> ChatProbeResult:
    """Test both capabilities and explain an unsupported candidate."""
    streaming = await probe_streaming(model)
    tool_calling = await probe_tool_calling(model)
    result = ChatProbeResult(streaming=streaming, tool_calling=tool_calling)
    return ChatProbeResult(
        streaming=streaming,
        tool_calling=tool_calling,
        message=None if result.verified else _describe_probe(result),
    )
