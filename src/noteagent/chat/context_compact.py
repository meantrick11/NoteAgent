"""Pure functions that decide and execute context compaction.

No database or HTTP here: everything operates on ``MessageRecord`` lists and
``ContextBudget`` so the algorithm is unit-testable in isolation.
"""

from dataclasses import dataclass

from noteagent.chat.context_budget import ContextBudget
from noteagent.chat.context_tokens import estimate_tokens
from noteagent.chat.history import MessageRecord


@dataclass(slots=True)
class TurnBundle:
    """One turn's persistent records with its token cost and completeness."""

    turn_id: str
    records: list[MessageRecord]
    tokens: int
    complete: bool  # True iff there is at least one role=='assistant' in records


def _record_tokens(record: MessageRecord) -> int:
    """Token cost of one record. Tool stubs count name+args+preview once."""
    if record.role == "tool":
        preview = record.output_preview or record.content or ""
        return sum(
            estimate_tokens(part)
            for part in (record.tool_name or "", record.tool_arguments or "", preview)
        )
    return estimate_tokens(record.content or "")


def group_turns(records: list[MessageRecord]) -> list[TurnBundle]:
    """Group consecutive records by turn_id. Order = first appearance.

    Rows with turn_id None each become their own bundle, complete iff the row
    is an assistant message.
    """
    bundles: list[TurnBundle] = []
    index: dict[str, int] = {}
    for record in records:
        if record.turn_id is None:
            bundles.append(
                TurnBundle(
                    turn_id=record.id,
                    records=[record],
                    tokens=_record_tokens(record),
                    complete=record.role == "assistant",
                )
            )
            continue
        key = record.turn_id
        if key not in index:
            index[key] = len(bundles)
            bundles.append(TurnBundle(turn_id=key, records=[], tokens=0, complete=False))
        bundle = bundles[index[key]]
        bundle.records.append(record)
        bundle.tokens += _record_tokens(record)
        if record.role == "assistant":
            bundle.complete = True
    return bundles


def compute_f(
    *,
    system: str,
    tool_defs: str,
    summary: str,
    current_user: str,
    draft_line: str | None,
    runtime: str,
    budget: ContextBudget,
) -> int:
    """Sum the token cost of the non-history pack contents plus reserves."""
    total = (
        estimate_tokens(system)
        + estimate_tokens(tool_defs)
        + estimate_tokens(summary)
        + estimate_tokens(current_user)
        + estimate_tokens(draft_line or "")
        + estimate_tokens(runtime)
        + budget.output_reserve
        + budget.safety_buffer
    )
    return total


def select_turns_to_drop(
    bundles: list[TurnBundle],
    *,
    current_turn_id: str,
    k_tokens: int,
) -> tuple[list[TurnBundle], list[TurnBundle]]:
    """Split bundles into (drop, keep) around the token budget K.

    The current turn is never dropped. Among the remaining bundles, only
    complete turns are droppable; incomplete non-current turns are kept. Walk
    complete turns newest-to-oldest accumulating tokens; keep the newest
    complete turn even if it alone exceeds k_tokens. Keep order is chronological
    (old -> new) with the current turn appended last.
    """
    current = [b for b in bundles if b.turn_id == current_turn_id]
    others = [b for b in bundles if b.turn_id != current_turn_id]
    complete = [
        b for b in others
        if b.complete and (not b.records or all(r.turn_id is not None for r in b.records))
    ]
    incomplete = [b for b in others if b not in complete]
    keep_rev: list[TurnBundle] = []
    used = 0
    for b in reversed(complete):
        if keep_rev and used + b.tokens > k_tokens:
            break
        if not keep_rev and b.tokens > k_tokens:
            keep_rev.append(b)
            break
        keep_rev.append(b)
        used += b.tokens
    keep_completed = list(reversed(keep_rev))
    keep_ids = {x.turn_id for x in keep_completed}
    drop = [b for b in complete if b.turn_id not in keep_ids]  # complete 已是旧→新
    keep = incomplete + keep_completed + current
    return drop, keep


def format_turns_for_summary(bundles: list[TurnBundle]) -> str:
    """Plain text dump of dropped turns for the summarizer (role/content/stub)."""
    lines: list[str] = []
    for bundle in bundles:
        lines.append(f"Turn {bundle.turn_id}:")
        for record in bundle.records:
            if record.role == "tool":
                lines.append(
                    f"  [tool] name={record.tool_name or ''} "
                    f"preview={record.output_preview or ''} status={record.status or ''}"
                )
            else:
                lines.append(f"  [{record.role}] {record.content}")
    return "\n".join(lines)


def concat_summary(old: str | None, chunk: str) -> str:
    """Append a new summary chunk to the old one, separated by a blank line."""
    if old is None or not old.strip():
        return chunk.strip()
    return old.rstrip() + "\n\n" + chunk.strip()


def should_compact(pack_tokens: int, budget: ContextBudget) -> bool:
    """Return True when the pack already meets the trigger threshold."""
    return pack_tokens >= budget.trigger_tokens()
