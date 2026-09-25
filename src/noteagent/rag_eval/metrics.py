"""Pure scoring helpers for RAG evidence metrics.

This module does no I/O and never loads a model: it turns already-computed
retrieval outcomes into numbers, so the metric tests stay offline and fast.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Interval:
    """A half-open character range [start, end) inside one note."""

    note_id: str
    start: int
    end: int


def _merge(intervals: list[Interval]) -> list[Interval]:
    """Union overlapping or touching intervals, per note, preserving document order."""
    merged: list[Interval] = []
    for item in sorted(intervals, key=lambda i: (i.note_id, i.start, i.end)):
        previous = merged[-1] if merged else None
        # 相邻（end == start）也算连续：它是消费者一次读到的相邻区域，中间没有空洞。
        if previous is not None and previous.note_id == item.note_id and item.start <= previous.end:
            merged[-1] = Interval(
                note_id=previous.note_id,
                start=previous.start,
                end=max(previous.end, item.end),
            )
        else:
            merged.append(item)
    return merged


def covered_units(
    hits: list[Interval],
    units: dict[str, list[Interval]],
) -> set[str]:
    """Unit ids with at least one alternative fully covered by the hits.

    Only the fragments actually handed to the consumer are passed in as ``hits``.
    Fragments from the same note may be merged first, so a unit split across two
    overlapping neighbours still counts; a gap between two fragments never does.
    """
    merged = _merge(hits)
    found: set[str] = set()
    for unit_id, alternatives in units.items():
        for alternative in alternatives:
            if any(
                hit.note_id == alternative.note_id
                and hit.start <= alternative.start
                and hit.end >= alternative.end
                for hit in merged
            ):
                found.add(unit_id)
                break
    return found


def evidence_recall(covered: set[str], required: set[str]) -> float:
    """Share of required evidence units covered by the retrieved fragments."""
    return len(covered & required) / len(required)


def reciprocal_rank(ranking: list[set[str]], k: int = 5) -> float:
    """1/rank of the first fragment that covers any unit; 0.0 when none do."""
    return next(
        (1.0 / rank for rank, units in enumerate(ranking[:k], 1) if units),
        0.0,
    )


def hit_at(ranking: list[set[str]], k: int = 3) -> bool:
    """True if one of the first k fragments covers at least one unit on its own."""
    return any(ranking[:k])
