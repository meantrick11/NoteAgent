"""Run the direct retrieval evaluation against the production retrieval stack.

The runner builds a private index per run, asks the real ``RetrievalService``
for each annotated query, and scores the returned fragments against the frozen
evidence annotations. Nothing here touches the production notes, Chroma path or
chat database.
"""

from __future__ import annotations

import hashlib
import json
import logging
import platform
import statistics
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from noteagent.bootstrap.settings import Settings, project_root
from noteagent.notes.repository import FileNoteRepository
from noteagent.rag_eval.dataset import Corpus, QueryCase, heading_path_at, load_corpus, load_queries
from noteagent.rag_eval.metrics import Interval, covered_units, evidence_recall, hit_at, reciprocal_rank
from noteagent.retrieval.chunker import MarkdownChunker
from noteagent.retrieval.embedder import SentenceTransformerEmbedder
from noteagent.retrieval.service import RetrievalService
from noteagent.retrieval.vector_store import ChromaVectorStore

_logger = logging.getLogger(__name__)

DEFAULT_TOP_K = 5
DEFAULT_PROBE_K = 20
DEFAULT_REPEATS = 3
DEFAULT_WARMUP = 5


@dataclass(frozen=True, slots=True)
class HitRecord:
    """One returned fragment, located back into the frozen note when possible."""

    rank: int
    file_name: str
    chunk_index: int | None
    distance: float
    content: str
    note_id: str | None
    heading_path: str | None
    start_char: int | None
    end_char: int | None
    mapping_error: str | None


@dataclass(frozen=True, slots=True)
class QueryOutcome:
    """Scored outcome of one query, ready for JSONL and aggregation."""

    query_id: str
    group_id: str
    split: str
    category: str
    answerable: bool
    query: str
    required_units: list[str]
    per_rank_units: list[list[str]]
    covered_units: list[str]
    recall_at_k: float | None
    hit_at_3: bool | None
    mrr_at_k: float | None
    covered_at_probe: list[str]
    recall_at_probe_k: float | None
    failure: str | None
    hits: list[HitRecord] = field(default_factory=list)


def chunk_spans(text: str, chunks: list[str], overlap: int) -> list[Interval | None]:
    """Locate each produced chunk back in the source text.

    Mirrors the splitter's own offset arithmetic and then verifies the slice, so a
    repeated passage can never be located by guessing: an unverifiable chunk stays
    ``None`` and is reported as a mapping error instead of being silently dropped.
    """
    spans: list[Interval | None] = []
    cursor = 0
    for index, chunk in enumerate(chunks):
        guess = max(0, cursor - overlap) if index else 0
        start = text.find(chunk, guess)
        if start == -1:
            start = text.find(chunk)
        if start == -1 or text[start : start + len(chunk)] != chunk:
            spans.append(None)
            continue
        spans.append(Interval(note_id="", start=start, end=start + len(chunk)))
        cursor = start + len(chunk)
    return spans


def build_index(
    corpus: Corpus,
    run_dir: Path,
    chunker: MarkdownChunker,
    embedder: SentenceTransformerEmbedder,
    collection_name: str,
) -> RetrievalService:
    """Create a fresh private Chroma collection and index every manifest note."""
    store = ChromaVectorStore(run_dir / "chroma", collection_name)
    notes = FileNoteRepository(corpus.root / "notes")
    service = RetrievalService(
        notes=notes,
        chunker=chunker,
        embedder=embedder,
        store=store,
    )
    for record in corpus.notes.values():
        written = service.index_note(record.file)
        _logger.info("indexed note_id=%s file=%s chunks=%d", record.note_id, record.file, written)
    return service


def _span_lookup(
    corpus: Corpus,
    chunker: MarkdownChunker,
    overlap: int,
) -> dict[str, tuple[list[str], list[Interval | None]]]:
    """Pre-compute chunk texts and their verified spans for every note."""
    lookup: dict[str, tuple[list[str], list[Interval | None]]] = {}
    for note_id, text in corpus.texts.items():
        chunks = chunker.split(text)
        spans = chunk_spans(text, chunks, overlap)
        lookup[note_id] = (chunks, spans)
    return lookup


def _note_id_of(corpus: Corpus, file_name: str) -> str | None:
    """Map a stored relative file path back to its manifest note_id."""
    stem = Path(file_name).stem
    return stem if stem in corpus.notes else None


def evaluate_query(
    query: QueryCase,
    *,
    corpus: Corpus,
    service: RetrievalService,
    lookup: dict[str, tuple[list[str], list[Interval | None]]],
    top_k: int,
    probe_k: int,
) -> QueryOutcome:
    """Search once with a deeper probe, then score the first top_k fragments.

    The deeper probe costs nothing extra (the query embedding is computed once) and
    lets a miss be classified as "ranked below top_k" instead of only "not found".
    """
    units = corpus.required_units(query)
    hits = [hit for hit in service.search(query.query, top_k=probe_k) if hit.content]
    records: list[HitRecord] = []
    intervals: list[Interval] = []
    for rank, hit in enumerate(hits, start=1):
        file_name = str((hit.metadata or {}).get("file_name") or "")
        raw_index = (hit.metadata or {}).get("chunk_index")
        chunk_index = int(raw_index) if raw_index is not None else None
        note_id = _note_id_of(corpus, file_name)
        interval: Interval | None = None
        error: str | None = None
        if note_id is None:
            error = f"unknown note for file_name={file_name!r}"
        elif chunk_index is None:
            error = "chunk_index missing from metadata"
        else:
            chunks, spans = lookup[note_id]
            if not 0 <= chunk_index < len(spans):
                error = f"chunk_index {chunk_index} outside {len(spans)} chunks"
            elif spans[chunk_index] is None:
                error = "chunk text could not be located in the note"
            else:
                span = spans[chunk_index]
                interval = Interval(note_id, span.start, span.end)
        heading = (
            heading_path_at(corpus.headings[note_id], interval.start)
            if interval is not None and note_id is not None
            else None
        )
        records.append(
            HitRecord(
                rank=rank,
                file_name=file_name,
                chunk_index=chunk_index,
                distance=float(hit.distance),
                content=hit.content,
                note_id=note_id,
                heading_path=heading,
                start_char=None if interval is None else interval.start,
                end_char=None if interval is None else interval.end,
                mapping_error=error,
            )
        )
        if interval is not None:
            intervals.append(interval)

    required = set(units)
    if not query.answerable:
        return QueryOutcome(
            query_id=query.id,
            group_id=query.group_id,
            split=query.split,
            category=query.category,
            answerable=False,
            query=query.query,
            required_units=[],
            per_rank_units=[],
            covered_units=[],
            recall_at_k=None,
            hit_at_3=None,
            mrr_at_k=None,
            covered_at_probe=[],
            recall_at_probe_k=None,
            failure=None,
            hits=records,
        )

    in_top = intervals[:top_k]
    per_rank_sets = [covered_units([interval], units) for interval in in_top]
    covered = covered_units(in_top, units)
    covered_probe = covered_units(intervals[:probe_k], units)
    recall = evidence_recall(covered, required)
    failure = (
        None
        if recall == 1.0
        else classify_failure(records[:top_k], required, covered, covered_probe)
    )
    return QueryOutcome(
        query_id=query.id,
        group_id=query.group_id,
        split=query.split,
        category=query.category,
        answerable=True,
        query=query.query,
        required_units=sorted(required),
        per_rank_units=[sorted(item) for item in per_rank_sets],
        covered_units=sorted(covered),
        recall_at_k=recall,
        hit_at_3=hit_at(per_rank_sets, 3),
        mrr_at_k=reciprocal_rank(per_rank_sets, top_k),
        covered_at_probe=sorted(covered_probe),
        recall_at_probe_k=evidence_recall(covered_probe, required),
        failure=failure,
        hits=records,
    )


def classify_failure(
    records: list[HitRecord],
    required: set[str],
    covered: set[str],
    covered_at_probe: set[str],
) -> str:
    """Name the dominant reason a query missed evidence.

    ``covered_at_probe`` only contains units the deeper probe reached, so a unit
    found there but not in the delivered top_k is a ranking problem, not a missing
    one. Anything absent even from the probe is either not retrieved or not
    covered by a single fragment (mapped as evidence_not_in_returned_fragments).
    """
    if any(record.mapping_error for record in records):
        return "mapping_error"
    if not records:
        return "no_fragments"
    if covered_at_probe == required:
        # 放到更深的候选里就能覆盖全部 unit：纯粹是名次问题。
        return "ranked_below_top_k"
    if covered:
        return "partial_evidence"
    if covered_at_probe:
        return "ranked_below_top_k"
    return "evidence_not_in_returned_fragments"


def measure_latency(
    service: RetrievalService,
    queries: list[QueryCase],
    *,
    repeats: int,
    warmup: int,
) -> dict[str, float | int | None]:
    """Warm up, then repeat every query to report hot-query latency percentiles."""
    if not queries:
        return {"queries": 0, "repeats": repeats, "samples": 0, "p50_ms": None, "p95_ms": None}
    for index in range(warmup):
        service.search(queries[index % len(queries)].query, top_k=DEFAULT_TOP_K)
    samples: list[float] = []
    for _ in range(repeats):
        for query in queries:
            started = time.monotonic()
            service.search(query.query, top_k=DEFAULT_TOP_K)
            samples.append((time.monotonic() - started) * 1000)
    samples.sort()
    return {
        "queries": len(queries),
        "repeats": repeats,
        "samples": len(samples),
        # min 是受同机其他进程干扰最小的样本，跨 run 比较延迟时用它。
        "min_ms": round(samples[0], 2),
        "p50_ms": round(statistics.median(samples), 2),
        "p95_ms": round(samples[max(0, int(len(samples) * 0.95) - 1)], 2),
    }


def _sha256(path: Path) -> str:
    """Hash a file so a report can prove which data it used."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_state() -> dict[str, str]:
    """Current commit and dirty flag, so runs are comparable."""
    def _run(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=project_root(), capture_output=True, text=True, check=False
        ).stdout.strip()

    return {"commit": _run("rev-parse", "HEAD"), "status": _run("status", "--short")}


def _model_revision(cache_dir: Path, model_name: str) -> str | None:
    """Resolve the cached snapshot commit for a sentence-transformers model."""
    folder = f"models--{model_name.replace('/', '--')}"
    ref = cache_dir / folder / "refs" / "main"
    return ref.read_text(encoding="utf-8").strip() if ref.is_file() else None


def run_retrieval_eval(
    *,
    corpus_dir: Path,
    queries_path: Path,
    split: str,
    variant: str,
    run_id: str,
    var_root: Path,
    results_root: Path,
    top_k: int = DEFAULT_TOP_K,
    probe_k: int = DEFAULT_PROBE_K,
    repeats: int = DEFAULT_REPEATS,
    warmup: int = DEFAULT_WARMUP,
) -> dict:
    """Full direct-retrieval run: index, score, report. Returns the summary dict."""
    corpus = load_corpus(corpus_dir)
    all_queries = load_queries(queries_path, corpus)
    queries = [query for query in all_queries if query.split == split]
    if not queries:
        raise ValueError(f"no queries with split={split!r} in {queries_path}")

    run_dir = var_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    chunk_size, chunk_overlap = 500, 50
    chunker = MarkdownChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    settings = Settings()
    settings_model = settings.embedding_model
    embedder = SentenceTransformerEmbedder(
        settings_model,
        settings.embedding_cache_dir,
        local_files_only=settings.embedding_local_files_only,
    )
    collection = f"raggrade-{variant}-{corpus_dir.name}-{settings_model.replace('/', '_')}"[:63]
    index_started = time.monotonic()
    lookup = _span_lookup(corpus, chunker, chunk_overlap)
    service = build_index(corpus, run_dir, chunker, embedder, collection)
    index_ms = round((time.monotonic() - index_started) * 1000)

    outcomes: list[QueryOutcome] = []
    for query in queries:
        outcome = evaluate_query(
            query,
            corpus=corpus,
            service=service,
            lookup=lookup,
            top_k=top_k,
            probe_k=max(probe_k, top_k),
        )
        outcomes.append(outcome)
        _logger.info(
            "query scored id=%s answerable=%s recall=%s probe=%s hit3=%s failure=%s",
            outcome.query_id,
            outcome.answerable,
            outcome.recall_at_k,
            outcome.recall_at_probe_k,
            outcome.hit_at_3,
            outcome.failure,
        )

    answerable = [item for item in outcomes if item.answerable]
    unanswerable = [item for item in outcomes if not item.answerable]
    latency = measure_latency(service, queries, repeats=repeats, warmup=warmup)

    def _rate(items: list[QueryOutcome], predicate) -> dict[str, object]:
        passed = sum(1 for item in items if predicate(item))
        return {
            "passed": passed,
            "total": len(items),
            "rate": None if not items else round(passed / len(items), 4),
        }

    by_category: dict[str, dict[str, object]] = {}
    for category in sorted({item.category for item in answerable}):
        group = [item for item in answerable if item.category == category]
        by_category[category] = {
            "recall_at_k": _rate(group, lambda i: i.recall_at_k == 1.0),
            "mean_recall_at_k": round(
                statistics.mean([i.recall_at_k for i in group if i.recall_at_k is not None]), 4
            ),
            "hit_at_3": _rate(group, lambda i: bool(i.hit_at_3)),
            "mrr_at_k": round(
                statistics.mean([i.mrr_at_k for i in group if i.mrr_at_k is not None]), 4
            ),
            "mean_recall_at_probe_k": round(
                statistics.mean(
                    [i.recall_at_probe_k for i in group if i.recall_at_probe_k is not None]
                ),
                4,
            ),
        }
    summary = {
        "run_id": run_id,
        "variant": variant,
        "split": split,
        "corpus": str(corpus_dir),
        "queries_path": str(queries_path),
        "top_k": top_k,
        "probe_k": max(probe_k, top_k),
        "answerable": {
            "full_recall_at_k": _rate(answerable, lambda i: i.recall_at_k == 1.0),
            "mean_recall_at_k": round(
                statistics.mean([i.recall_at_k for i in answerable if i.recall_at_k is not None]), 4
            ),
            "hit_at_3": _rate(answerable, lambda i: bool(i.hit_at_3)),
            "mrr_at_k": round(
                statistics.mean([i.mrr_at_k for i in answerable if i.mrr_at_k is not None]), 4
            ),
            "mean_recall_at_probe_k": round(
                statistics.mean(
                    [i.recall_at_probe_k for i in answerable if i.recall_at_probe_k is not None]
                ),
                4,
            ),
            "full_recall_at_probe_k": _rate(answerable, lambda i: i.recall_at_probe_k == 1.0),
            "mapping_errors": sum(
                1 for item in answerable for hit in item.hits if hit.mapping_error
            ),
        },
        "unanswerable": {
            "count": len(unanswerable),
            "top1_distance": sorted(
                round(item.hits[0].distance, 4) for item in unanswerable if item.hits
            ),
        },
        "by_category": by_category,
        "failures": {
            item.query_id: item.failure for item in answerable if item.failure is not None
        },
        "unanswerable_ids": [item.query_id for item in unanswerable],
        "latency": latency,
        "index_ms": index_ms,
    }
    config = {
        "run_id": run_id,
        "variant": variant,
        "split": split,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "git": _git_state(),
        "corpus_dir": str(corpus_dir),
        "corpus_manifest_sha256": _sha256(corpus_dir / "manifest.jsonl"),
        "note_sha256": {nid: rec.sha256 for nid, rec in corpus.notes.items()},
        "queries_path": str(queries_path),
        "queries_sha256": _sha256(queries_path),
        "embedding_model": settings_model,
        "embedding_revision": _model_revision(settings.embedding_cache_dir, settings_model),
        "embedding_normalized": False,
        "chunker": {"chunk_size": chunk_size, "chunk_overlap": chunk_overlap},
        "collection": collection,
        "chroma_dir": str(run_dir / "chroma"),
        "distance": "chroma-default-l2",
        "top_k": top_k,
        "probe_k": max(probe_k, top_k),
        "repeats": repeats,
        "warmup": warmup,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "processor": platform.processor(),
    }
    _write_outputs(
        run_id=run_id,
        run_dir=run_dir,
        results_root=results_root,
        config=config,
        summary=summary,
        outcomes=outcomes,
    )
    return summary


def _write_outputs(
    *,
    run_id: str,
    run_dir: Path,
    results_root: Path,
    config: dict,
    summary: dict,
    outcomes: list[QueryOutcome],
) -> None:
    """Write the full (local) run artifacts plus a body-free committed summary."""
    (run_dir / "config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (run_dir / "results.jsonl").open("w", encoding="utf-8") as handle:
        for item in outcomes:
            handle.write(
                json.dumps(
                    {
                        "query_id": item.query_id,
                        "group_id": item.group_id,
                        "split": item.split,
                        "category": item.category,
                        "answerable": item.answerable,
                        "query": item.query,
                        "required_units": item.required_units,
                        "per_rank_units": [sorted(units) for units in item.per_rank_units],
                        "covered_units": item.covered_units,
                        "recall_at_k": item.recall_at_k,
                        "hit_at_3": item.hit_at_3,
                        "mrr_at_k": item.mrr_at_k,
                        "covered_at_probe": item.covered_at_probe,
                        "recall_at_probe_k": item.recall_at_probe_k,
                        "failure": item.failure,
                        "hits": [asdict(record) for record in item.hits],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    (run_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (run_dir / "report.md").write_text(
        _render_report(config, summary, outcomes, with_bodies=True), encoding="utf-8"
    )
    committed = results_root / run_id
    committed.mkdir(parents=True, exist_ok=True)
    (committed / "config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (committed / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (committed / "summary.md").write_text(
        _render_report(config, summary, outcomes, with_bodies=False), encoding="utf-8"
    )
    _logger.info("run written run_dir=%s committed=%s", run_dir, committed)


def _render_report(
    config: dict,
    summary: dict,
    outcomes: list[QueryOutcome],
    *,
    with_bodies: bool,
) -> str:
    """Markdown report; ``with_bodies`` keeps the verbatim hits that stay local."""
    lines = [
        f"# Retrieval eval {summary['run_id']}",
        "",
        f"- variant: `{summary['variant']}` split: `{summary['split']}` top_k: {summary['top_k']} "
        f"probe_k: {summary['probe_k']}",
        f"- model: `{config['embedding_model']}` revision `{config['embedding_revision']}`",
        f"- chunker: {config['chunker']} distance: {config['distance']}",
        f"- corpus manifest sha256: `{config['corpus_manifest_sha256']}`",
        f"- queries sha256: `{config['queries_sha256']}`",
        f"- git: `{config['git']['commit']}` dirty: {'yes' if config['git']['status'] else 'no'}",
        f"- index build: {summary['index_ms']} ms",
        "",
        "## Metrics",
        "",
        "| set | metric | passed/total | rate |",
        "|---|---|---|---|",
        f"| answerable | full Evidence Recall@{summary['top_k']} | "
        f"{summary['answerable']['full_recall_at_k']['passed']}/{summary['answerable']['full_recall_at_k']['total']} "
        f"| {summary['answerable']['full_recall_at_k']['rate']} |",
        f"| answerable | Evidence Hit@3 | {summary['answerable']['hit_at_3']['passed']}/"
        f"{summary['answerable']['hit_at_3']['total']} | {summary['answerable']['hit_at_3']['rate']} |",
        f"| answerable | mean Evidence Recall@{summary['top_k']} | - | "
        f"{summary['answerable']['mean_recall_at_k']} |",
        f"| answerable | MRR@{summary['top_k']} | - | {summary['answerable']['mrr_at_k']} |",
        f"| answerable (diagnostic) | mean Evidence Recall@{summary['probe_k']} | - | "
        f"{summary['answerable']['mean_recall_at_probe_k']} |",
        f"| answerable (diagnostic) | full Recall@{summary['probe_k']} | "
        f"{summary['answerable']['full_recall_at_probe_k']['passed']}/"
        f"{summary['answerable']['full_recall_at_probe_k']['total']} | "
        f"{summary['answerable']['full_recall_at_probe_k']['rate']} |",
        "",
        "## By category",
        "",
        "| category | full recall@k | hit@3 | mean recall@k | mrr | mean recall@probe |",
        "|---|---|---|---|---|---|",
    ]
    for category, stats in summary["by_category"].items():
        lines.append(
            f"| {category} | {stats['recall_at_k']['passed']}/{stats['recall_at_k']['total']} "
            f"| {stats['hit_at_3']['passed']}/{stats['hit_at_3']['total']} "
            f"| {stats['mean_recall_at_k']} | {stats['mrr_at_k']} "
            f"| {stats['mean_recall_at_probe_k']} |"
        )
    lines += [
        "",
        "## Latency (hot queries)",
        "",
        f"- samples: {summary['latency']['samples']} "
        f"(warmup {summary['latency']['repeats']}x{summary['latency']['queries']})",
        f"- min: {summary['latency']['min_ms']} ms, p50: {summary['latency']['p50_ms']} ms, "
        f"p95: {summary['latency']['p95_ms']} ms",
        f"- index build: {summary['index_ms']} ms",
        "- 同机其他进程会显著干扰本机延迟；跨 run 比较以 min 为准，并注明测量时段。",
        "",
        "## Failures",
        "",
        "失败分类：`ranked_below_top_k` 放到更深候选就能覆盖；`partial_evidence` 只覆盖了部分"
        " unit；`evidence_not_in_returned_fragments` 返回的片段里没有可完整覆盖的证据；"
        "`mapping_error` 片段无法映射回原文；`no_fragments` 检索为空。",
        "",
        "| query | category | recall@k | recall@probe | hit@3 | failure | top hit (file, distance) |",
        "|---|---|---|---|---|---|---|",
    ]
    for item in outcomes:
        if not item.answerable or item.failure is None:
            continue
        top = item.hits[0] if item.hits else None
        where = f"{top.file_name}, {round(top.distance, 4)}" if top else "-"
        lines.append(
            f"| {item.query_id} | {item.category} | {item.recall_at_k} "
            f"| {item.recall_at_probe_k} | {item.hit_at_3} | {item.failure} | {where} |"
        )
    if not with_bodies:
        lines += [
            "",
            "> 命中正文与逐条位置只保存在本地 `var/evals/rag/<run-id>/`（隐私语料）。",
        ]
    lines += [
        "",
        "## Unanswerable queries",
        "",
        f"- ids: {', '.join(summary['unanswerable_ids']) or '(none)'}",
        f"- top-1 distances: {summary['unanswerable']['top1_distance']}",
        "- 检索层无阈值，故这些查询仍会返回片段；正确处理在 Agent 层评价。",
        "",
    ]
    if with_bodies:
        lines += [
            "## Retrieved fragments",
            "",
            f"只列出前 {summary['top_k']} 条；更深的 probe（{summary['probe_k']} 条）逐条见 `results.jsonl`。",
            "",
        ]
        for item in outcomes:
            lines.append(f"### {item.query_id} ({item.category})")
            lines.append("")
            lines.append(f"- query: {item.query}")
            lines.append(f"- required units: {item.required_units}")
            lines.append(f"- per rank: {item.per_rank_units}")
            for record in item.hits[: summary["top_k"]]:
                location = (
                    f"{record.note_id}[{record.start_char}:{record.end_char}] "
                    f"{record.heading_path}"
                    if record.note_id and record.start_char is not None
                    else f"mapping_error={record.mapping_error}"
                )
                lines.append("")
                lines.append(
                    f"**#{record.rank}** {record.file_name} chunk {record.chunk_index} "
                    f"distance {round(record.distance, 4)} — {location}"
                )
                lines.append("")
                lines.append("```text")
                lines.append(record.content)
                lines.append("```")
            lines.append("")
    return "\n".join(lines)
