"""Per-turn citation ids for search/read. Mapping stays server-side."""

from __future__ import annotations

import logging
import re
from contextvars import ContextVar
from dataclasses import dataclass

_logger = logging.getLogger(__name__)

CITE_RE = re.compile(r"\[\[cite:(\d+)\]\]")


@dataclass(frozen=True, slots=True)
class Citation:
    """One source the model may cite by index in this turn."""

    index: int
    file_name: str
    chunk_index: int | None
    quote: str | None

    def as_dict(self) -> dict[str, object]:
        """JSON shape stored on the assistant message."""
        return {
            "index": self.index,
            "file_name": self.file_name,
            "chunk_index": self.chunk_index,
            "quote": self.quote,
        }


class CitationRegistry:
    """Assign stable 1-based ids for this turn. Duplicate sources reuse an id."""

    def __init__(self) -> None:
        self._by_key: dict[tuple[str, int | None, str], Citation] = {}
        self._by_index: dict[int, Citation] = {}
        self._next = 1

    def register(
        self,
        *,
        file_name: str,
        chunk_index: int | None = None,
        quote: str | None = None,
    ) -> int:
        """Return a 1-based source_id; reuse it when file_name, chunk_index, and quote match."""
        key = (file_name, chunk_index, quote or "")
        existing = self._by_key.get(key)
        if existing is not None:
            return existing.index
        cite = Citation(
            index=self._next,
            file_name=file_name,
            chunk_index=chunk_index,
            quote=quote,
        )
        self._next += 1
        self._by_key[key] = cite
        self._by_index[cite.index] = cite
        _logger.info(
            "citation register index=%s file=%s chunk=%s",
            cite.index,
            file_name,
            chunk_index,
        )
        return cite.index

    def get(self, index: int) -> Citation | None:
        """Lookup a registered source, or None if the model invented the id."""
        return self._by_index.get(index)


current_citations: ContextVar[CitationRegistry | None] = ContextVar(
    "noteagent_citations",
    default=None,
)


def strip_cite_markers(text: str) -> str:
    """Remove [[cite:N]] so history packs do not leak prior-turn ids."""
    return CITE_RE.sub("", text)


def sanitize_answer(text: str, registry: CitationRegistry) -> tuple[str, list[dict[str, object]]]:
    """Keep registered [[cite:N]] tags; remumber used sources 1..n in first-seen order."""
    old_to_new: dict[int, int] = {}
    used: list[Citation] = []
    dropped = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal dropped
        old = int(match.group(1))
        cite = registry.get(old)
        if cite is None:
            dropped += 1
            return ""
        new = old_to_new.get(old)
        if new is None:
            new = len(old_to_new) + 1
            old_to_new[old] = new
            used.append(
                Citation(
                    index=new,
                    file_name=cite.file_name,
                    chunk_index=cite.chunk_index,
                    quote=cite.quote,
                )
            )
        return f"[[cite:{new}]]"

    cleaned = CITE_RE.sub(repl, text)
    ordered = [cite.as_dict() for cite in used]
    _logger.info("citation sanitize kept=%d dropped=%d", len(ordered), dropped)
    return cleaned, ordered
