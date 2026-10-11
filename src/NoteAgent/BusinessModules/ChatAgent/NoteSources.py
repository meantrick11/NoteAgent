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
_URL_RE = re.compile(r"https?://[^\s<>\"'，。、；：(（）)】\]]+")

# Web tool statuses that mean the article body was actually obtained.
FETCHED_OK = frozenset({"ok", "partial"})
FETCHED_FAILED = frozenset({"login_required", "blocked", "unsupported", "failed"})


@dataclass(frozen=True)
class SourceEvidence:
    """What this conversation actually did with URLs, used to verify a draft's sources."""

    user_urls: tuple[str, ...]
    fetched_ok: frozenset[str]
    fetched_failed: frozenset[str]
    user_provided_after_failure: frozenset[str] = frozenset()


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


def source_urls_in_section(content: str) -> tuple[list[str], list[str]]:
    """Read URLs already approved in a note's trailing source section."""
    matches = list(_SOURCE_SECTION_RE.finditer(content))
    if not matches:
        return [], []
    fetched: list[str] = []
    provided: list[str] = []
    for line in content[matches[-1].end():].splitlines():
        if not line.startswith("- "):
            continue
        urls = extract_urls(line.split("（", 1)[0])
        if not urls:
            continue
        (provided if USER_PROVIDED_NOTE in line else fetched).append(urls[0])
    return dedupe_urls(fetched), dedupe_urls(provided)


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
    """Read the original URL from a structured webpage tool step."""
    try:
        args = json.loads(str(step.get("arguments") or "") or "{}")
    except ValueError:
        return None
    return args.get("url") if isinstance(args, dict) else None


def build_source_evidence(
    user_texts: Iterable[str], steps: Iterable[dict], *,
    history: Iterable[dict] = (), current_question: str = "",
) -> SourceEvidence:
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
    history_rows = list(history)
    historical_steps = [
        step for row in history_rows if row.get("role") == "assistant"
        for step in (row.get("tool_steps") or [])
    ]
    for step in [*historical_steps, *steps]:
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
    # A failed fetch can be marked user-provided only after a later user message
    # supplies substantial text. If several URLs failed, the message must name the
    # matching URL so an unrelated paste cannot certify all of them.
    pending: set[str] = set()
    provided_after_failure: set[str] = set()
    awaiting_paste = False
    for row in [*history_rows, {"role": "user", "content": current_question}]:
        if row.get("role") == "assistant":
            for step in row.get("tool_steps") or []:
                if step.get("name") == "read_webpage" and step.get("web_status") in FETCHED_FAILED:
                    name = normalize_url(_url_from_step(step) or "")
                    if name:
                        pending.add(name)
            answer = str(row.get("content") or "").lower()
            awaiting_paste = bool(pending and ("paste" in answer or "粘贴" in answer))
        elif row.get("role") == "user" and pending:
            content = str(row.get("content") or "")
            body = content
            prompted = awaiting_paste
            awaiting_paste = False
            for url in extract_urls(content):
                body = body.replace(url, "")
            if len(body.strip()) < 20:
                continue
            named = pending.intersection(extract_urls(content))
            if named:
                provided_after_failure.update(named)
            elif len(pending) == 1 and (_declares_pasted_body(body) or prompted):
                provided_after_failure.update(pending)
    return SourceEvidence(
        tuple(user_urls), frozenset(ok), frozenset(failed),
        frozenset(provided_after_failure),
    )


def _declares_pasted_body(text: str) -> bool:
    """Require an explicit paste cue when the user did not repeat the URL."""
    prefix = text.strip().lower()[:100]
    return any(cue in prefix for cue in (
        "网页正文", "网页内容", "粘贴的内容", "粘贴的正文", "以下是正文",
        "here is the article", "here is the page", "pasted article", "pasted page",
    ))


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
        and url in evidence.user_provided_after_failure
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
    "source_urls_in_section",
    "strip_source_section",
]
