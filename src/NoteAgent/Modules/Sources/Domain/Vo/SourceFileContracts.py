"""Shared source-file states, parse limits and parser output."""
from dataclasses import dataclass
from typing import Callable, Literal

SourceStatus = Literal["stored", "queued", "parsing", "ready", "failed", "deleted"]
MAX_PAGES = 100
MAX_PIXELS = 16_000_000
MAX_CHARACTERS = 200_000
Vision = Callable[[bytes, str], str]


class ParseError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedFragment:
    locator: str
    text: str
