"""Fenced-code-aware Markdown heading parsing.

The parser lives here, not in the evaluation package, because indexing needs it too
and `retrieval` must never depend on `rag_eval`.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

_logger = logging.getLogger(__name__)

_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.*?)[ \t]*$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")


@dataclass(frozen=True, slots=True)
class Heading:
    """One Markdown heading, with its joined path and its own char range."""

    level: int
    text: str
    path: str
    start: int
    end: int


def note_headings(text: str) -> tuple[Heading, ...]:
    """Parse ATX headings, ignoring ``#`` lines inside fenced code blocks.

    Corpus evidence: one real note has seven comment lines shaped exactly like an H1
    inside fences, so a plain text scan would invent headings out of code comments.
    """
    headings: list[Heading] = []
    stack: list[tuple[int, str]] = []
    offset = 0
    in_fence = False
    for line in text.splitlines(keepends=True):
        stripped = line.rstrip("\n").rstrip("\r")
        if _FENCE_RE.match(stripped):
            in_fence = not in_fence
        elif not in_fence:
            match = _HEADING_RE.match(stripped)
            if match and match.group(2):
                level = len(match.group(1))
                label = match.group(2)
                while stack and stack[-1][0] >= level:
                    stack.pop()
                stack.append((level, label))
                headings.append(
                    Heading(
                        level=level,
                        text=label,
                        path=" > ".join(item[1] for item in stack),
                        start=offset,
                        end=offset + len(line),
                    )
                )
        offset += len(line)
    if in_fence:
        _logger.warning("note ends inside an unclosed code fence")
    return tuple(headings)


def heading_path_at(headings: tuple[Heading, ...], offset: int) -> str:
    """Path of the innermost heading whose section contains ``offset``.

    Returns an empty string when the offset sits before the first heading.
    """
    path = ""
    for heading in headings:
        if heading.start <= offset:
            path = heading.path
        else:
            break
    return path
