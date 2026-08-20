import logging
import time

from langchain_core.callbacks import BaseCallbackHandler

logger = logging.getLogger(__name__)


class AgentTraceHandler(BaseCallbackHandler):
    """Log LLM and tool start/end/error with elapsed milliseconds."""

    def __init__(self):
        self._starts: dict[str, float] = {}
        self._tool_names: dict[str, str] = {}

    def _elapsed_ms(self, run_id: str) -> int:
        """Milliseconds since the matching start event; 0 if start was missing."""
        return round((time.monotonic() - self._starts.pop(run_id, time.monotonic())) * 1000)

    def on_llm_start(self, serialized, prompts, *, run_id, **kwargs):
        self._starts[run_id] = time.monotonic()
        prompt_len = sum(len(p) for p in prompts) if prompts else 0
        logger.info(
            "LLM start  model=%s  prompt_chars=%d",
            serialized.get("name", "?"),
            prompt_len,
        )

    def _reply_preview(self, response) -> str:
        """First generation text, truncated by the log format."""
        generations = getattr(response, "generations", None) or []
        if not generations or not generations[0]:
            return ""
        first = generations[0][0]
        text = getattr(first, "text", "") or ""
        if text:
            return text
        message = getattr(first, "message", None)
        content = getattr(message, "content", "") if message else ""
        return content if isinstance(content, str) else str(content or "")

    def on_llm_end(self, response, *, run_id, **kwargs):
        llm_output = getattr(response, "llm_output", None) or {}
        usage = (
            getattr(response, "usage_metadata", None)
            or llm_output.get("token_usage")
            or {}
        )
        logger.info(
            "LLM end  duration=%dms  tokens_in=%s  tokens_out=%s  reply=%.300s",
            self._elapsed_ms(run_id),
            usage.get("input_tokens", usage.get("prompt_tokens", "?")),
            usage.get("output_tokens", usage.get("completion_tokens", "?")),
            self._reply_preview(response),
        )

    def on_llm_error(self, error, *, run_id, **kwargs):
        logger.error("LLM error  duration=%dms  error=%s", self._elapsed_ms(run_id), error)

    def on_tool_start(self, serialized, input_str, *, run_id, **kwargs):
        self._starts[run_id] = time.monotonic()
        name = serialized.get("name", "?")
        self._tool_names[run_id] = name
        logger.info("Tool start  tool=%s  input=%.200s", name, input_str)

    def on_tool_end(self, output, *, run_id, **kwargs):
        name = self._tool_names.pop(run_id, "?")
        logger.info(
            "Tool end  tool=%s  duration=%dms  output=%.200s",
            name,
            self._elapsed_ms(run_id),
            str(output),
        )

    def on_tool_error(self, error, *, run_id, **kwargs):
        name = self._tool_names.pop(run_id, "?")
        logger.error(
            "Tool error  tool=%s  duration=%dms  error=%s",
            name,
            self._elapsed_ms(run_id),
            error,
        )
