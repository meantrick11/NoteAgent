"""Context-window budget derived from Settings.

All compression/stub thresholds flow through ``ContextBudget`` so that the
compact and agent modules never hardcode numbers like 32768, 0.8, 0.6 or 1000.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from noteagent.bootstrap.settings import Settings


@dataclass(frozen=True)
class ContextBudget:
    """Immutable context-window budget for a chat session."""

    window: int
    trigger_ratio: float
    target_ratio: float
    stub_preview_tokens: int
    args_preview_chars: int
    output_reserve: int
    safety_buffer: int
    max_tool_hops: int = 8  # max tool-call rounds per stream(); from Settings

    def trigger_tokens(self) -> int:
        """Return int(window * trigger_ratio)."""
        return int(self.window * self.trigger_ratio)

    def target_tokens(self) -> int:
        """Return int(window * target_ratio)."""
        return int(self.window * self.target_ratio)


def budget_from_settings(settings: "Settings") -> ContextBudget:
    """Map Settings fields onto ContextBudget."""
    return ContextBudget(
        window=settings.chat_context_window,
        trigger_ratio=settings.context_trigger_ratio,
        target_ratio=settings.context_target_ratio,
        stub_preview_tokens=settings.context_stub_preview_tokens,
        args_preview_chars=settings.context_args_preview_chars,
        output_reserve=settings.context_output_reserve,
        safety_buffer=settings.context_safety_buffer,
        max_tool_hops=settings.chat_max_tool_hops,
    )
