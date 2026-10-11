"""Pure rules for the trailing webpage source block (REQ-009)."""

from __future__ import annotations

from NoteAgent.BusinessModules.ChatAgent.NoteSources import (
    SOURCE_SECTION_TITLE,
    USER_PROVIDED_NOTE,
    SourceEvidence,
    build_source_evidence,
    dedupe_urls,
    merge_source_section,
    normalize_url,
    render_source_section,
    select_sources,
)

U1 = "https://example.com/gil"
U2 = "https://example.com/rust"


def test_normalize_url_accepts_only_plain_http_https():
    assert normalize_url(U1) == U1
    assert normalize_url("http://a.test/x") == "http://a.test/x"
    assert normalize_url("ftp://a.test/x") is None
    assert normalize_url("a.test/x") is None
    assert normalize_url("http://user:pass@a.test/x") is None
    assert normalize_url("") is None
    assert normalize_url("  https://a.test/y  ") == "https://a.test/y"


def test_dedupe_keeps_first_use_order():
    assert dedupe_urls([U2, U1, U2, "bad", U1]) == [U2, U1]


def test_render_lists_sources_in_order_with_user_provided_marker():
    section = render_source_section([U2, U1], [U1, "https://x.test/pasted"])
    assert section is not None
    assert section.startswith(SOURCE_SECTION_TITLE)
    body = section.splitlines()[2:]
    assert body[0] == f"- {U2}"
    assert body[1] == f"- {U1}"
    assert body[2] == f"- https://x.test/pasted（{USER_PROVIDED_NOTE}）"


def test_render_is_none_without_sources():
    assert render_source_section([], []) is None
    assert render_source_section(["bad"], ["also bad"]) is None


def test_merge_replaces_any_previous_section():
    old = "## 标题\n\n正文\n\n## 来源\n\n- https://old.test/x\n"
    merged = merge_source_section(old, render_source_section([U1], []))
    assert merged.count(SOURCE_SECTION_TITLE) == 1
    assert U1 in merged
    assert "https://old.test/x" not in merged
    assert merged.rstrip().endswith(U1)


def test_merge_without_source_section_leaves_content_untouched():
    content = "## 标题\n\n正文\n"
    assert merge_source_section(content, None) == content


def test_merge_with_none_removes_an_existing_section():
    content = "## 标题\n\n正文\n\n## 来源\n\n- https://old.test/x\n"
    merged = merge_source_section(content, None)
    assert SOURCE_SECTION_TITLE not in merged
    assert merged == "## 标题\n\n正文"


def test_merge_on_create_body_returns_just_the_section():
    merged = merge_source_section("", render_source_section([U1], []))
    assert merged.startswith(SOURCE_SECTION_TITLE)
    assert U1 in merged


def _steps(*entries) -> list[dict]:
    return [
        {"name": "read_webpage", "web_status": status, "arguments": f'{{"url": "{url}"}}'}
        for url, status in entries
    ]


def test_build_source_evidence_splits_ok_and_failed_from_steps():
    evidence = build_source_evidence(
        [f"读一下 {U1} 和 {U2}", "还有 https://example.com/bad"],
        _steps((U1, "ok"), (U2, "partial"), ("https://example.com/bad", "failed")),
    )
    assert evidence.user_urls == (U1, U2, "https://example.com/bad")
    assert evidence.fetched_ok == frozenset({U1, U2})
    assert evidence.fetched_failed == frozenset({"https://example.com/bad"})


def test_extract_urls_ignores_trailing_chinese_punctuation():
    evidence = build_source_evidence(["看这个 " + U1 + "，还有别的"], [])
    assert evidence.user_urls == (U1,)


def test_select_sources_drops_unverified_claims():
    evidence = SourceEvidence(
        user_urls=(U1,), fetched_ok=frozenset({U1}), fetched_failed=frozenset()
    )
    sources, provided = select_sources([U1, "https://not-given.test/x"], [], evidence)
    assert sources == [U1]
    assert provided == []


def test_select_sources_requires_a_failed_fetch_for_user_provided():
    evidence = SourceEvidence(
        user_urls=(U1,), fetched_ok=frozenset({U1}), fetched_failed=frozenset()
    )
    sources, provided = select_sources([], [U1], evidence)
    assert sources == []
    assert provided == []


def test_select_sources_keeps_user_provided_after_a_failed_fetch():
    evidence = SourceEvidence(
        user_urls=(U1,), fetched_ok=frozenset(), fetched_failed=frozenset({U1})
    )
    sources, provided = select_sources([], [U1], evidence)
    assert sources == []
    assert provided == [U1]


def test_select_sources_without_evidence_keeps_nothing():
    assert select_sources([U1], [U2], None) == ([], [])
