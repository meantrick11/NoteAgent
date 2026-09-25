"""Offline unit tests for RAG evidence metrics. No model, no Chroma, no network."""

import hashlib
import json
from pathlib import Path

import pytest

from noteagent.rag_eval.dataset import DatasetError, load_corpus, load_queries
from noteagent.retrieval.markdown import heading_path_at, note_headings
from noteagent.rag_eval.metrics import (
    Interval,
    covered_units,
    evidence_recall,
    hit_at,
    reciprocal_rank,
)


def test_partial_evidence_and_duplicate_hits():
    covered = set().union({"u1"}, {"u1"})
    assert evidence_recall(covered, {"u1", "u2"}) == 0.5


def test_rank_uses_first_actual_evidence():
    assert reciprocal_rank([set(), {"u1"}, {"u1"}]) == 0.5
    assert reciprocal_rank([set(), set()]) == 0.0


def test_reciprocal_rank_respects_k():
    assert reciprocal_rank([set(), {"u1"}], k=1) == 0.0


def test_hit_at_looks_only_at_first_three():
    assert hit_at([set(), set(), {"u1"}]) is True
    assert hit_at([set(), set(), set(), {"u1"}]) is False


def test_same_note_wrong_section_does_not_count():
    units = {"u1": [Interval("Backtracking.md", 100, 160)]}
    hits = [Interval("Backtracking.md", 300, 360), Interval("BinaryTree.md", 100, 160)]
    assert covered_units(hits, units) == set()
    assert evidence_recall(covered_units(hits, units), {"u1"}) == 0.0


def test_overlapping_neighbours_merge_but_a_gap_does_not():
    unit = {"u1": [Interval("SQLAlchemy_psycopg.md", 100, 200)]}
    # 相邻两块拼起来正好盖住证据区间：算覆盖。
    assert covered_units(
        [Interval("SQLAlchemy_psycopg.md", 100, 160), Interval("SQLAlchemy_psycopg.md", 160, 200)],
        unit,
    ) == {"u1"}
    # 中间留洞：不算覆盖。
    assert covered_units(
        [Interval("SQLAlchemy_psycopg.md", 100, 150), Interval("SQLAlchemy_psycopg.md", 180, 200)],
        unit,
    ) == set()


def test_an_alternative_in_another_note_also_counts():
    units = {
        "u1": [
            Interval("Python_Tutorial_Intro.md", 0, 40),
            Interval("BinaryTree.md", 500, 560),
        ]
    }
    hits = [Interval("BinaryTree.md", 480, 600)]
    assert covered_units(hits, units) == {"u1"}


def test_one_hit_can_cover_several_units_without_extra_credit():
    units = {
        "u1": [Interval("Backtracking.md", 100, 150)],
        "u2": [Interval("Backtracking.md", 120, 200)],
    }
    hits = [Interval("Backtracking.md", 100, 200), Interval("Backtracking.md", 100, 200)]
    covered = covered_units(hits, units)
    assert covered == {"u1", "u2"}
    assert evidence_recall(covered, {"u1", "u2"}) == 1.0


# --- dataset loading and validation -------------------------------------------

NOTE_BODY = """# Alpha

## 第一节

回溯法的模板由三部分组成。

## 第二节

队列用于广度优先遍历。
"""


def _make_corpus(tmp_path: Path, body: str = NOTE_BODY) -> Path:
    """Write a one-note frozen corpus and return its directory."""
    corpus_dir = tmp_path / "corpus"
    (corpus_dir / "notes").mkdir(parents=True)
    raw = body.encode("utf-8")
    (corpus_dir / "notes" / "Alpha.md").write_bytes(raw)
    manifest = {
        "note_id": "Alpha",
        "file": "Alpha.md",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "origin_path": "notes/Alpha.md",
        "source_file": None,
        "source_status": "missing",
        "review_status": "provisional",
        "issues": [],
    }
    (corpus_dir / "manifest.jsonl").write_text(
        json.dumps(manifest, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return corpus_dir


def _evidence(body: str, snippet: str, heading_path: str = "Alpha > 第一节") -> dict:
    """Build one evidence location from a verbatim snippet of the note body."""
    start = body.index(snippet)
    return {
        "note_id": "Alpha",
        "heading_path": heading_path,
        "start_char": start,
        "end_char": start + len(snippet),
        "quote": snippet,
    }


def _write_queries(tmp_path: Path, rows: list[dict]) -> Path:
    """Write a query set to disk as JSONL."""
    path = tmp_path / "queries.jsonl"
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    return path


def _good_rows(body: str = NOTE_BODY) -> list[dict]:
    """One answerable dev query plus one near-miss unanswerable query."""
    snippet = "回溯法的模板由三部分组成。"
    return [
        {
            "id": "q-answerable",
            "group_id": "g1",
            "split": "dev",
            "query": "回溯法的模板包含什么？",
            "category": "fact",
            "answerable": True,
            "evidence_units": [
                {
                    "id": "u1",
                    "fact": "模板由三部分组成",
                    "alternatives": [_evidence(body, snippet)],
                }
            ],
        },
        {
            "id": "q-near-miss",
            "group_id": "g2",
            "split": "dev",
            "query": "回溯法在分布式事务里的隔离级别是什么？",
            "category": "unanswerable",
            "answerable": False,
            "evidence_units": [],
        },
    ]


def test_good_query_set_loads(tmp_path: Path):
    corpus = load_corpus(_make_corpus(tmp_path))
    queries = load_queries(_write_queries(tmp_path, _good_rows()), corpus)
    assert [q.id for q in queries] == ["q-answerable", "q-near-miss"]
    units = corpus.required_units(queries[0])
    assert units == {"u1": [Interval("Alpha", NOTE_BODY.index("回溯法"), NOTE_BODY.index("回溯法") + len("回溯法的模板由三部分组成。"))]}


def test_corpus_rejects_edited_note(tmp_path: Path):
    corpus_dir = _make_corpus(tmp_path)
    (corpus_dir / "notes" / "Alpha.md").write_text("# Alpha\n\n改过了。\n", encoding="utf-8")
    with pytest.raises(DatasetError, match="sha256 mismatch"):
        load_corpus(corpus_dir)


def test_rejects_quote_that_does_not_match_offsets(tmp_path: Path):
    corpus = load_corpus(_make_corpus(tmp_path))
    rows = _good_rows()
    rows[0]["evidence_units"][0]["alternatives"][0]["quote"] = "回溯法的模板由四部分组成。"
    with pytest.raises(DatasetError, match="quote does not match"):
        load_queries(_write_queries(tmp_path, rows), corpus)


def test_rejects_reversed_range(tmp_path: Path):
    corpus = load_corpus(_make_corpus(tmp_path))
    rows = _good_rows()
    location = rows[0]["evidence_units"][0]["alternatives"][0]
    location["start_char"], location["end_char"] = location["end_char"], location["start_char"]
    with pytest.raises(DatasetError, match="start_char must be below end_char"):
        load_queries(_write_queries(tmp_path, rows), corpus)


def test_rejects_unknown_note_id(tmp_path: Path):
    corpus = load_corpus(_make_corpus(tmp_path))
    rows = _good_rows()
    rows[0]["evidence_units"][0]["alternatives"][0]["note_id"] = "Ghost"
    with pytest.raises(DatasetError, match="unknown note_id"):
        load_queries(_write_queries(tmp_path, rows), corpus)


def test_rejects_heading_path_that_is_not_in_the_note(tmp_path: Path):
    corpus = load_corpus(_make_corpus(tmp_path))
    rows = _good_rows()
    rows[0]["evidence_units"][0]["alternatives"][0]["heading_path"] = "Alpha > 不存在的节"
    with pytest.raises(DatasetError, match="is not a heading path"):
        load_queries(_write_queries(tmp_path, rows), corpus)


def test_rejects_unanswerable_query_carrying_evidence(tmp_path: Path):
    corpus = load_corpus(_make_corpus(tmp_path))
    rows = _good_rows()
    rows[1]["evidence_units"] = rows[0]["evidence_units"]
    with pytest.raises(DatasetError, match="unanswerable query must have no evidence"):
        load_queries(_write_queries(tmp_path, rows), corpus)


def test_rejects_answerable_query_without_evidence(tmp_path: Path):
    corpus = load_corpus(_make_corpus(tmp_path))
    rows = _good_rows()
    rows[0]["evidence_units"] = []
    with pytest.raises(DatasetError, match="answerable query needs category evidence and units"):
        load_queries(_write_queries(tmp_path, rows), corpus)


def test_rejects_group_split_across_dev_and_holdout(tmp_path: Path):
    corpus = load_corpus(_make_corpus(tmp_path))
    rows = _good_rows()
    rows.append(
        {
            "id": "q-holdout-twin",
            "group_id": "g1",
            "split": "holdout",
            "query": "回溯法的模板由几部分组成？",
            "category": "paraphrase",
            "answerable": True,
            "evidence_units": rows[0]["evidence_units"],
        }
    )
    with pytest.raises(DatasetError, match="appears in both splits"):
        load_queries(_write_queries(tmp_path, rows), corpus)


def test_rejects_unanswerable_that_is_off_topic(tmp_path: Path):
    corpus = load_corpus(_make_corpus(tmp_path))
    rows = _good_rows()
    rows[1]["query"] = "Rust 的所有权规则如何影响生命周期标注？"
    with pytest.raises(DatasetError, match="near-misses"):
        load_queries(_write_queries(tmp_path, rows), corpus)


def test_headings_ignore_hash_lines_inside_code_fences(tmp_path: Path):
    body = "# Alpha\n\n## 代码\n\n```python\n# 这是注释，不是标题\nx = 1\n```\n\n## 下一节\n\n正文。\n"
    headings = note_headings(body)
    assert [h.path for h in headings] == ["Alpha", "Alpha > 代码", "Alpha > 下一节"]
    code_offset = body.index("# 这是注释")
    fence_close = body.index("```\n\n## 下一节")
    assert heading_path_at(headings, code_offset) == "Alpha > 代码"
    assert heading_path_at(headings, fence_close) == "Alpha > 代码"
    assert heading_path_at(headings, body.index("正文。")) == "Alpha > 下一节"


# --- chunk -> note offset mapping and failure classification -------------------


def test_chunk_spans_locate_every_production_chunk():
    from noteagent.retrieval.chunker import MarkdownChunker

    from noteagent.rag_eval.run import chunk_spans

    body = ("# 标题\n\n" + "第一段内容。" * 40 + "\n\n" + "第二段内容。" * 40 + "\n")
    chunker = MarkdownChunker(chunk_size=200, chunk_overlap=20)
    chunks = chunker.split(body)
    spans = chunk_spans(body, chunks, 20)
    assert len(spans) == len(chunks)
    assert all(span is not None for span in spans)
    for chunk, span in zip(chunks, spans):
        assert body[span.start : span.end] == chunk
    starts = [span.start for span in spans if span is not None]
    assert starts == sorted(starts)


def test_chunk_spans_finds_the_repeated_occurrence_in_order():
    from noteagent.rag_eval.run import chunk_spans

    repeated = "完全相同的重复段落。"
    body = f"{repeated}\n\n{repeated}\n\n结尾。\n"
    chunks = [repeated, repeated]
    spans = chunk_spans(body, chunks, 0)
    assert [span.start for span in spans if span is not None] == [
        body.index(repeated),
        body.index(repeated, body.index(repeated) + 1),
    ]


def _hit(rank: int, *, note_id: str | None = "Alpha", error: str | None = None) -> object:
    from noteagent.rag_eval.run import HitRecord

    return HitRecord(
        rank=rank,
        file_name="Alpha.md",
        chunk_index=rank - 1,
        distance=0.5,
        content="text",
        note_id=note_id,
        heading_path=None,
        start_char=0,
        end_char=4,
        mapping_error=error,
    )


def test_classify_failure_separates_ranking_from_recall():
    from noteagent.rag_eval.run import classify_failure

    required = {"u1"}
    assert classify_failure([_hit(1)], {"u1"}, set(), {"u1"}) == "ranked_below_top_k"
    assert classify_failure([_hit(1)], {"u1"}, set(), set()) == (
        "evidence_not_in_returned_fragments"
    )
    assert classify_failure([_hit(1, note_id=None, error="boom")], {"u1"}, set(), set()) == (
        "mapping_error"
    )
    assert classify_failure([], {"u1"}, set(), set()) == "no_fragments"
    assert classify_failure(
        [_hit(1)], {"u1", "u2"}, {"u1"}, {"u1", "u2"}
    ) == "ranked_below_top_k"
    assert classify_failure([_hit(1)], {"u1", "u2"}, {"u1"}, {"u1"}) == "partial_evidence"
