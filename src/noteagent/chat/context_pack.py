"""Assemble Persistent History + Runtime into the LangChain message pack.

The current turn's tool rows are excluded from the persistent transcript (their
full text lives in ``runtime_messages``), so the model never sees both the stub
line and the full ToolMessage for the same hop.
"""

from dataclasses import dataclass

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from noteagent.chat.context_budget import ContextBudget
from noteagent.chat.context_compact import compute_f
from noteagent.chat.context_tokens import estimate_tokens
from noteagent.chat.drafts import NoteDraft
from noteagent.chat.history import MessageRecord


def stub_text(record: MessageRecord) -> str:
    """One line: [tool_stub] name=... args=... preview=... status=... truncated=..."""
    return (
        f"[tool_stub] name={record.tool_name or ''} args={record.tool_arguments or ''} "
        f"preview={record.output_preview or ''} status={record.status or ''} "
        f"truncated={record.truncated}"
    )


def records_to_langchain(records: list[MessageRecord]) -> list:
    """Map Persistent records to LangChain messages; tool rows become stub lines."""
    out = []
    for record in records:
        if record.role == "user":
            out.append(HumanMessage(content=record.content))
        elif record.role == "assistant":
            out.append(AIMessage(content=record.content))
        elif record.role == "tool":
            out.append(AIMessage(content=stub_text(record)))
    return out


def draft_workspace_line(draft: NoteDraft | None) -> str | None:
    """None if no draft; else a one-line workspace notice for the model."""
    if draft is None:
        return None
    return f"待审草稿: {draft.action} {draft.file_name}（全文在前端卡片，不要当聊天正文）"


@dataclass(slots=True)
class PackResult:
    """The assembled message list plus its token accounting."""

    messages: list
    pack_tokens: int
    f_tokens: int
    k_tokens: int


def _content_text(message) -> str:
    """Extract the string content of a LangChain message for token counting."""
    content = getattr(message, "content", None)
    return content if isinstance(content, str) else ""


def build_pack(
    *,
    system_prompt: str,
    tool_defs: str,
    summary: str | None,
    persistent: list[MessageRecord],
    current_turn_id: str,
    current_user: str,
    draft_line: str | None,
    runtime_messages: list,
    budget: ContextBudget,
) -> PackResult:
    """Build the external/internal pack and compute F/K/token budget."""
    hist = [
        r for r in persistent
        if not (r.role == "tool" and r.turn_id == current_turn_id)
    ]
    messages = [SystemMessage(content=system_prompt)]
    if summary:
        messages.append(SystemMessage(content="历史摘要：\n" + summary))
    if draft_line:
        messages.append(SystemMessage(content=draft_line))
    messages.extend(records_to_langchain(hist))
    if not any(r.role == "user" and r.turn_id == current_turn_id for r in hist):
        messages.append(HumanMessage(content=current_user))
    messages.extend(runtime_messages)

    runtime_text = "\n".join(_content_text(m) for m in runtime_messages)
    f_tokens = compute_f(
        system=system_prompt,
        tool_defs=tool_defs,
        summary=summary or "",
        current_user=current_user,
        draft_line=draft_line,
        runtime=runtime_text,
        budget=budget,
    )
    k_tokens = max(0, budget.target_tokens() - f_tokens)
    pack_text = tool_defs + "\n".join(_content_text(m) for m in messages)
    pack_tokens = estimate_tokens(pack_text)
    return PackResult(
        messages=messages,
        pack_tokens=pack_tokens,
        f_tokens=f_tokens,
        k_tokens=k_tokens,
    )
