"""Source-section rules for webpage-backed notes (REQ-009).

Pure helpers only: URL validation, de-duplication, and rendering/merging the trailing
``## 来源`` block. Nothing here stores a page body — the section carries URLs alone, and
a URL whose fetch failed is only listed when the user supplied the content by hand.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from contextvars import ContextVar
from dataclasses import dataclass
from urllib.parse import urlsplit

SOURCE_SECTION_TITLE = "## 来源"
USER_PROVIDED_NOTE = "内容由用户提供，网页未成功获取"

# A markdown heading line ``## 来源`` (also tolerates extra spaces).
_SOURCE_SECTION_RE = re.compile(r"(?m)^##\s*来源\s*$")
# Enough to spot the URLs in a user message; CJK punctuation ends the URL.
_URL_RE = re.compile(r"https?://[^\s<>\"'，。、；：）)】\]]+")

# Web tool statuses that mean the article body was actually obtained.
FETCHED_OK = frozenset({"ok", "partial"})
FETCHED_FAILED = frozenset({"login_required", "blocked", "unsupported", "failed"})


@dataclass(frozen=True)
class SourceEvidence:
    """What this conversation actually did with URLs, used to verify a draft's sources."""

    user_urls: tuple[str, ...]
    fetched_ok: frozenset[str]
    fetched_failed: frozenset[str]


current_source_evidence: ContextVar[SourceEvidence | None] = ContextVar(
    "noteagent_source_evidence", default=None
)


def normalize_url(url: str) -> str | None:
    """A usable http(s) URL, or None. Credentials in the URL are refused."""
    candidate = (url or "").strip()
    if not candidate:
        return None
    parts = urlsplit(candidate)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    if parts.username or parts.password:
        return None
    return candidate


def dedupe_urls(urls: Iterable[str]) -> list[str]:
    """Valid URLs, first occurrence wins, order preserved."""
    seen: set[str] = set()
    out: list[str] = []
    for url in urls:
        name = normalize_url(url)
        if name is None or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def render_source_section(source_urls: Iterable[str], user_supplied_urls: Iterable[str]) -> str | None:
    """The trailing source block, or None when there is nothing to list."""
    fetched = dedupe_urls(source_urls)
    fetched_set = set(fetched)
    provided = [url for url in dedupe_urls(user_supplied_urls) if url not in fetched_set]
    lines = [f"- {url}" for url in fetched]
    lines += [f"- {url}（{USER_PROVIDED_NOTE}）" for url in provided]
    if not lines:
        return None
    return SOURCE_SECTION_TITLE + "\n\n" + "\n".join(lines) + "\n"


def strip_source_section(content: str) -> str:
    """Drop a trailing ``## 来源`` block, so re-rendering never appends a second one."""
    match = None
    for found in _SOURCE_SECTION_RE.finditer(content):
        match = found
    if match is None:
        return content
    head = content[: match.start()].rstrip()
    return head


def merge_source_section(content: str, section: str | None) -> str:
    """Replace any existing source block with ``section``; None just removes it."""
    body = strip_source_section(content)
    if section is None:
        return body
    body = body.rstrip()
    return f"{body}\n\n{section}" if body else section


def extract_urls(text: str) -> list[str]:
    """http(s) URLs mentioned in a message, in order."""
    return [match.group(0) for match in _URL_RE.finditer(text or "")]


def _url_from_step(step: dict) -> str | None:
    try:
        args = json.loads(str(step.get("arguments") or "") or "{}")
    except ValueError:
        return None
    return args.get("url") if isinstance(args, dict) else None


def build_source_evidence(user_texts: Iterable[str], steps: Iterable[dict]) -> SourceEvidence:
    """Collect the session's user-provided URLs and how each webpage read turned out."""
    user_urls: list[str] = []
    seen: set[str] = set()
    for text in user_texts:
        for url in extract_urls(text):
            name = normalize_url(url)
            if name is not None and name not in seen:
                seen.add(name)
                user_urls.append(name)
    ok: set[str] = set()
    failed: set[str] = set()
    for step in steps:
        if str(step.get("name") or "") != "read_webpage":
            continue
        name = normalize_url(_url_from_step(step) or "")
        if name is None:
            continue
        status = str(step.get("web_status") or "")
        if status in FETCHED_OK:
            ok.add(name)
        elif status in FETCHED_FAILED:
            failed.add(name)
    return SourceEvidence(tuple(user_urls), frozenset(ok), frozenset(failed))


def select_sources(
    claimed: Iterable[str],
    claimed_user_provided: Iterable[str],
    evidence: SourceEvidence | None,
) -> tuple[list[str], list[str]]:
    """Keep only sources this session can prove: user-given, and read or failed.

    A successful source needs a webpage step that returned the body; a user-supplied
    source needs a failed fetch and the user's own message. Without evidence nothing is
    kept, so an unverifiable URL never reaches the note.
    """
    if evidence is None:
        return [], []
    sources = [
        url
        for url in dedupe_urls(claimed)
        if url in evidence.user_urls and url in evidence.fetched_ok
    ]
    provided = [
        url
        for url in dedupe_urls(claimed_user_provided)
        if url in evidence.user_urls
        and url in evidence.fetched_failed
        and url not in set(sources)
    ]
    return sources, provided


__all__ = [
    "SOURCE_SECTION_TITLE",
    "USER_PROVIDED_NOTE",
    "SourceEvidence",
    "build_source_evidence",
    "current_source_evidence",
    "dedupe_urls",
    "extract_urls",
    "merge_source_section",
    "normalize_url",
    "render_source_section",
    "select_sources",
    "strip_source_section",
]
