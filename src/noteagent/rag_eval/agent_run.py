"""Run the real ChatAgent over the frozen corpus and score the scenarios.

Each case gets its own notes copy, its own Chroma directory and its own sqlite
history, so a run can never touch the user's notes, the production index or the
chat database. Retrieval is the production stack; only the scoring is synthetic.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from noteagent.bootstrap.settings import Settings
from noteagent.chat.agent import ChatAgent
from noteagent.chat.context_budget import budget_from_settings
from noteagent.chat.drafts import WRITE_ACTIONS, DraftStore
from noteagent.chat.history import ConversationStore, start_turn
from noteagent.chat.tools import build_chat_tools
from noteagent.db import Base, create_engine_from_url, create_session_factory
from noteagent.notes.repository import FileNoteRepository
from noteagent.rag_eval.dataset import AgentCase, Corpus, QueryCase, heading_path_at
from noteagent.rag_eval.metrics import Interval, covered_units
from noteagent.rag_eval.run import HitRecord, chunk_spans
from noteagent.retrieval.chunker import MarkdownChunker
from noteagent.retrieval.embedder import SentenceTransformerEmbedder
from noteagent.retrieval.service import RetrievalService
from noteagent.retrieval.vector_store import ChromaVectorStore

_logger = logging.getLogger(__name__)

# 判定「明确说明没有历史依据」的关键词；命中情况会连原文一起落进报告，供人工复核。
NO_EVIDENCE_MARKERS = (
    "没有找到",
    "未找到",
    "没找到",
    "没有记录",
    "未记录",
    "没有保存",
    "没有相关",
    "没有关于",
    "笔记中没有",
    "笔记里没有",
    "没有查到",
    "没有搜到",
    "未查到",
    "未提及",
)

# 判定「识别出内容已存在、无需重复写入」的关键词。
DUPLICATE_MARKERS = (
    "已有",
    "已记录",
    "已经记录",
    "已存在",
    "已经存在",
    "已包含",
    "无需重复",
    "不需要重复",
    "重复",
)

DEFAULT_REPEATS = 3


@dataclass(frozen=True, slots=True)
class ToolStub:
    """One persisted tool row: the authoritative name, full arguments and status."""

    name: str
    arguments: str
    status: str | None


@dataclass(frozen=True, slots=True)
class SearchRecord:
    """One search_relative_from_chromadb call and the fragments it returned."""

    query: str
    top_k: int
    hits: list[HitRecord]


@dataclass(slots=True)
class CaseOutcome:
    """Everything one case run produced, plus the deterministic checks."""

    case_id: str
    split: str
    scenario: str
    repeat_index: int
    tools: list[str] = field(default_factory=list)
    tool_arguments: list[str] = field(default_factory=list)
    tool_statuses: list[str | None] = field(default_factory=list)
    searches: list[SearchRecord] = field(default_factory=list)
    read_files: list[str] = field(default_factory=list)
    draft: dict | None = None
    final_answer: str | None = None
    citations: list[dict] = field(default_factory=list)
    committed: bool = False
    checks: dict[str, bool | None] = field(default_factory=dict)
    task_success: bool | None = None
    task_success_strict: bool | None = None
    error: str | None = None
    elapsed_ms: int = 0


class RecordingRetrieval:
    """Wrap the production service to record every search the Agent performs."""

    def __init__(self, inner: RetrievalService, lookup: dict[str, tuple[list[str], list[Interval | None]]], corpus: Corpus):
        self._inner = inner
        self._lookup = lookup
        self._corpus = corpus
        self.searches: list[SearchRecord] = []

    def search(self, query: str, top_k: int = 3):
        """Record the call, then return the real fragments untouched."""
        hits = self._inner.search(query, top_k=top_k)
        records: list[HitRecord] = []
        for rank, hit in enumerate(hits, start=1):
            file_name = str((hit.metadata or {}).get("file_name") or "")
            raw_index = (hit.metadata or {}).get("chunk_index")
            chunk_index = int(raw_index) if raw_index is not None else None
            note_id = Path(file_name).stem if Path(file_name).stem in self._corpus.notes else None
            span: Interval | None = None
            if note_id is not None and chunk_index is not None:
                spans = self._lookup[note_id][1]
                if 0 <= chunk_index < len(spans):
                    span = spans[chunk_index]
            records.append(
                HitRecord(
                    rank=rank,
                    file_name=file_name,
                    chunk_index=chunk_index,
                    distance=float(hit.distance),
                    content=hit.content,
                    note_id=note_id,
                    heading_path=(
                        heading_path_at(self._corpus.headings[note_id], span.start)
                        if span is not None and note_id is not None
                        else None
                    ),
                    start_char=None if span is None else span.start,
                    end_char=None if span is None else span.end,
                    mapping_error=None if span is not None else "chunk not located",
                )
            )
        self.searches.append(SearchRecord(query=query, top_k=top_k, hits=records))
        return hits

    def index_note(self, file_name: str) -> int:
        """Delegate so an approved draft still re-indexes inside the sandbox."""
        return self._inner.index_note(file_name)

    def delete_note(self, file_name: str) -> None:
        """Delegate deletion for the same reason."""
        self._inner.delete_note(file_name)


def _copy_corpus_notes(corpus: Corpus, target: Path) -> None:
    """Copy every frozen note byte for byte into a case sandbox."""
    target.mkdir(parents=True, exist_ok=True)
    for record in corpus.notes.values():
        shutil.copy2(corpus.root / "notes" / record.file, target / record.file)


def build_sandbox(
    *,
    case_dir: Path,
    corpus: Corpus,
    model,
    settings: Settings,
    prompt_path: Path,
) -> tuple[ChatAgent, DraftStore, ConversationStore, FileNoteRepository, RecordingRetrieval]:
    """Create an isolated agent for one case: own notes, own index, own history."""
    notes_root = case_dir / "notes"
    _copy_corpus_notes(corpus, notes_root)
    notes = FileNoteRepository(notes_root)
    chunker = MarkdownChunker(500, 50)
    lookup: dict[str, tuple[list[str], list[Interval | None]]] = {}
    for note_id, text in corpus.texts.items():
        chunks = chunker.split(text)
        lookup[note_id] = (chunks, chunk_spans(text, chunks, 50))
    embedder = SentenceTransformerEmbedder(
        settings.embedding_model,
        settings.embedding_cache_dir,
        local_files_only=settings.embedding_local_files_only,
    )
    store = ChromaVectorStore(case_dir / "chroma", f"ragagent-{case_dir.name}"[:63])
    service = RetrievalService(notes=notes, chunker=chunker, embedder=embedder, store=store)
    for record in corpus.notes.values():
        service.index_note(record.file)
    retrieval = RecordingRetrieval(service, lookup, corpus)
    engine = create_engine_from_url("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    history = ConversationStore(create_session_factory(engine))
    drafts = DraftStore(history)
    agent = ChatAgent(
        model=model,
        tools=build_chat_tools(notes, retrieval, drafts),
        notes=notes,
        drafts=drafts,
        history=history,
        budget=budget_from_settings(settings),
        retrieval=retrieval,
        prompt_path=prompt_path,
    )
    return agent, drafts, history, notes, retrieval


def attach_tool_stubs(outcome: CaseOutcome, history: ConversationStore, conversation_id: str) -> None:
    """Use the persisted tool rows as the trajectory of record.

    The stream's ``tool`` event fires while the model is still emitting arguments, so it
    can carry ``{}``; the stub is written after execution with the full arguments and the
    real status. Names must agree, otherwise it is a harness bug and is recorded as one.
    """
    stubs: list[ToolStub] = []
    for record in history.list_persistent_after_watermark(conversation_id):
        if record.role != "tool" or not record.tool_name:
            continue
        stubs.append(
            ToolStub(
                name=record.tool_name,
                arguments=record.tool_arguments or "",
                status=record.status,
            )
        )
    if not stubs:
        if outcome.tools:
            outcome.error = "harness: tool events seen but no tool stub persisted"
            _logger.error("case %s harness mismatch: %s", outcome.case_id, outcome.error)
        return
    outcome.tools = [stub.name for stub in stubs]
    outcome.tool_arguments = [stub.arguments for stub in stubs]
    outcome.tool_statuses = [stub.status for stub in stubs]


def attach_searches(outcome: CaseOutcome, retrieval: RecordingRetrieval) -> None:
    """Hand the recorder's searches to the outcome, and refuse to measure silently wrong.

    The Agent's tool events prove a search happened; if the recorder disagrees, the
    metrics below would read "never searched" and quietly turn every history scenario
    into a failure. That mismatch is a harness bug, so it is recorded as an error.
    """
    outcome.searches = list(retrieval.searches)
    expected = [name for name in outcome.tools if name == "search_relative_from_chromadb"]
    if expected and not outcome.searches:
        outcome.error = (
            f"harness: {len(expected)} search tool call(s) but 0 recorded searches"
        )
        _logger.error("case %s harness mismatch: %s", outcome.case_id, outcome.error)


async def run_case(
    case: AgentCase,
    *,
    repeat_index: int,
    case_dir: Path,
    corpus: Corpus,
    queries: dict[str, QueryCase],
    model,
    settings: Settings,
    prompt_path: Path,
) -> CaseOutcome:
    """Play one scenario once against a fresh sandbox and score it deterministically."""
    started = time.monotonic()
    outcome = CaseOutcome(
        case_id=case.id,
        split=case.split,
        scenario=case.scenario,
        repeat_index=repeat_index,
    )
    agent, drafts, history, notes, retrieval = build_sandbox(
        case_dir=case_dir, corpus=corpus, model=model, settings=settings, prompt_path=prompt_path
    )
    record = history.create(case.id)
    # 前置对话按「一问一答一个 turn」写入，turn_id 必须是真实 UUID，否则短记忆打包会拒绝。
    for index in range(0, len(case.pre_dialogue), 2):
        pre_turn = start_turn()
        for role, content in case.pre_dialogue[index : index + 2]:
            history.append_message(record.id, role, content, turn_id=pre_turn)
    turn_id = start_turn()
    history.append_message(record.id, "user", case.user, turn_id=turn_id)

    loop = asyncio.get_running_loop()
    last_activity = loop.time()
    try:
        async for event in agent.stream(case.user, thread_id=record.id, turn_id=turn_id):
            kind = event.get("event")
            data = event.get("data")
            if kind == "tool" and isinstance(data, dict):
                # 流式阶段的 tool 事件可能只带部分参数，真正的参数以落库的 stub 为准。
                outcome.tools.append(str(data.get("name") or ""))
            elif kind == "assistant_final" and isinstance(data, str):
                outcome.final_answer = data
            elif kind == "sources" and isinstance(data, list):
                outcome.citations = [dict(item) for item in data]
            elif kind == "draft" and isinstance(data, dict):
                outcome.draft = dict(data)
            # 记录流式节奏，避免长时间无输出时看不出卡在哪一步。
            if loop.time() - last_activity > 30:
                _logger.info("case %s silent for %.0fs", case.id, loop.time() - last_activity)
            last_activity = loop.time()
    except Exception as exc:  # noqa: BLE001 - a failed run must stay a failed run
        outcome.error = f"{type(exc).__name__}: {exc}"
        _logger.exception("agent case failed id=%s repeat=%d", case.id, repeat_index)

    pending = drafts.get(record.id)
    if pending is not None and outcome.draft is None:
        outcome.draft = pending.as_dict()
    if pending is not None and pending.action in WRITE_ACTIONS:
        result = agent.review(record.id, "approve")
        outcome.committed = result.get("status") == "written"
        _logger.info("case %s draft applied result=%s", case.id, result)

    attach_tool_stubs(outcome, history, record.id)
    attach_searches(outcome, retrieval)
    outcome.checks = evaluate_checks(
        case,
        outcome,
        queries=queries,
        notes=notes,
        corpus=corpus,
    )
    outcome.task_success = _task_success(case, outcome)
    outcome.task_success_strict = _task_success(case, outcome, strict=True)
    outcome.elapsed_ms = round((time.monotonic() - started) * 1000)
    _logger.info(
        "case scored id=%s repeat=%d scenario=%s tools=%s success=%s error=%s",
        case.id,
        repeat_index,
        case.scenario,
        outcome.tools,
        outcome.task_success,
        outcome.error,
    )
    return outcome


def _unit_intervals(case: AgentCase, queries: dict[str, QueryCase], corpus: Corpus) -> dict[str, list[Interval]]:
    """Union the units of every referenced query into one requirement map."""
    units: dict[str, list[Interval]] = {}
    for ref in case.evidence_refs:
        for unit_id, intervals in corpus.required_units(queries[ref]).items():
            units[f"{ref}:{unit_id}"] = intervals
    return units


def _preserve_intervals(
    case: AgentCase, queries: dict[str, QueryCase], corpus: Corpus, refs: tuple[str, ...]
) -> list[str]:
    """Verbatim quotes referenced by a case, for the must-keep and must-not-repeat checks."""
    quotes: list[str] = []
    for ref in refs:
        for unit in queries[ref].evidence_units:
            quotes.extend(location.quote for location in unit.alternatives)
    return quotes


def evaluate_checks(
    case: AgentCase,
    outcome: CaseOutcome,
    *,
    queries: dict[str, QueryCase],
    notes: FileNoteRepository,
    corpus: Corpus,
) -> dict[str, bool | None]:
    """Deterministic checks only; nothing here judges prose quality."""
    checks: dict[str, bool | None] = {}
    searched = bool(outcome.searches)
    checks["search_called"] = searched == case.expect_search
    if case.expect_no_write:
        checks["no_write"] = outcome.draft is None
    action = None if outcome.draft is None else outcome.draft.get("action")
    file_name = None if outcome.draft is None else outcome.draft.get("file_name")
    # 没有提案时 action/目标不适用，记 None，避免把「按冲突要求先澄清」显示成失败。
    checks["action_ok"] = (
        None
        if case.expect_action is None or outcome.draft is None
        else action == case.expect_action
    )
    checks["target_ok"] = (
        None
        if case.target_file is None or outcome.draft is None
        else file_name == case.target_file
    )
    if case.expect_action is not None:
        checks["append_needs_read"] = (
            None if outcome.draft is None else _read_before_propose(case, outcome)
        )

    if case.evidence_refs:
        units = _unit_intervals(case, queries, corpus)
        checks["evidence_cited"] = (
            covered_units(_citation_intervals(outcome, corpus), units) == set(units)
        )
        # 严格口径：只认带回引文的检索引用（可定位到章节与原文）。
        checks["evidence_cited_search_only"] = (
            covered_units(_citation_intervals(outcome, corpus, quote_backed_only=True), units)
            == set(units)
        )
        searched_cover = covered_units(
            [Interval(h.note_id, h.start_char, h.end_char) for record in outcome.searches
             for h in record.hits if h.note_id and h.start_char is not None],
            units,
        )
        checks["retrieval_sufficient"] = searched_cover == set(units)
        checks["recovered_by_read"] = bool(
            checks["evidence_cited"]
            and not checks["evidence_cited_search_only"]
            and not checks["retrieval_sufficient"]
        )
    if case.scenario == "history_unanswerable":
        answer = outcome.final_answer or ""
        checks["states_no_evidence"] = any(marker in answer for marker in NO_EVIDENCE_MARKERS)
    if case.scenario == "history_append" and outcome.draft is None:
        answer = outcome.final_answer or ""
        checks["no_draft_explained"] = any(marker in answer for marker in DUPLICATE_MARKERS)
    if case.expect_flags_conflict:
        answer = outcome.final_answer or ""
        checks["flags_conflict"] = any(marker in answer for marker in case.conflict_markers)

    if case.target_file and outcome.draft is not None and outcome.committed:
        target = notes.read(notes.normalize(case.target_file))
        keep = _preserve_intervals(case, queries, corpus, case.must_preserve_refs)
        checks["must_preserve"] = all(quote in target for quote in keep) if keep else None
    else:
        checks["must_preserve"] = None
    if outcome.draft is not None:
        # 「不要重复已有内容」要看新写的草稿：原文本来就含这段，查整篇永远为假。
        forbid = _preserve_intervals(case, queries, corpus, case.must_not_contain_refs)
        draft_text = str(outcome.draft.get("content") or "")
        checks["must_not_contain"] = (
            not any(quote in draft_text for quote in forbid) if forbid else None
        )
    else:
        checks["must_not_contain"] = None
    if case.target_file is not None:
        # 有提案就必须真的写进沙箱副本，否则「原有事实还在」只是没改过的假象。
        checks["draft_applied"] = outcome.draft is None or outcome.committed
    return checks


def _read_before_propose(case: AgentCase, outcome: CaseOutcome) -> bool:
    """The target note must have been read before proposing to modify it."""
    if outcome.draft is None:
        return True
    try:
        propose_at = outcome.tools.index("propose_note")
    except ValueError:
        return False
    for index, name in enumerate(outcome.tools[:propose_at]):
        if name == "read_file" and case.target_file and case.target_file in outcome.tool_arguments[index]:
            return True
    return False


def _citation_intervals(
    outcome: CaseOutcome, corpus: Corpus, *, quote_backed_only: bool = False
) -> list[Interval]:
    """Map citations back to note intervals.

    A search citation carries the chunk quote, so it can be located precisely. A
    ``read_file`` citation carries only the file, which still means the Agent had that
    note's full text in front of it — that counts as covering evidence inside that note,
    and is reported separately so the strict, quote-backed measure stays visible.
    """
    intervals: list[Interval] = []
    for citation in outcome.citations:
        file_name = str(citation.get("file_name") or "")
        note_id = Path(file_name).stem
        if note_id not in corpus.notes:
            continue
        quote = citation.get("quote")
        if isinstance(quote, str) and quote:
            start = corpus.texts[note_id].find(quote)
            if start != -1:
                intervals.append(Interval(note_id, start, start + len(quote)))
        elif not quote_backed_only:
            intervals.append(Interval(note_id, 0, len(corpus.texts[note_id])))
    return intervals


def _task_success(case: AgentCase, outcome: CaseOutcome, *, strict: bool = False) -> bool:
    """One deterministic verdict per scenario; evidence stays in the report.

    补充场景接受两种结果：真的提案（action/目标/读后提案/保留/不重复都不能是 False），
    或者不提案但明确说明内容已存在、或按冲突要求先澄清。

    ``strict`` 只用于历史问答：要求引用是带回引文的检索引用，而不是靠 read_file 整篇兜底。
    """
    checks = outcome.checks
    if outcome.error is not None:
        return False
    if case.scenario == "plain_chat":
        return not outcome.searches and outcome.draft is None
    if case.scenario == "history_answer":
        key = "evidence_cited_search_only" if strict else "evidence_cited"
        return bool(checks.get("search_called")) and bool(checks.get(key))
    if case.scenario == "history_unanswerable":
        return (
            bool(checks.get("search_called"))
            and bool(checks.get("states_no_evidence"))
            and outcome.draft is None
        )
    # 补充场景不强制调用检索：用户已点名目标笔记时，list_files + read_file 是合法路径
    # （计划也允许中间出现 list_files）。检索调用率单独作为指标报告，不并进任务成败。
    if outcome.draft is None:
        if case.expect_flags_conflict:
            return bool(checks.get("flags_conflict"))
        return bool(checks.get("no_draft_explained"))
    parts = [
        checks.get("action_ok"),
        checks.get("target_ok"),
        checks.get("append_needs_read"),
        checks.get("draft_applied"),
        checks.get("must_preserve"),
        checks.get("must_not_contain"),
    ]
    if case.expect_flags_conflict:
        parts.append(checks.get("flags_conflict"))
    return all(item is not False for item in parts)


def summarize(outcomes: list[CaseOutcome]) -> dict:
    """Aggregate the plan's Agent metrics, split by scenario, with counts."""
    history = [item for item in outcomes if item.scenario != "plain_chat"]
    plain = [item for item in outcomes if item.scenario == "plain_chat"]

    def rate(items: list[CaseOutcome], predicate) -> dict[str, object]:
        passed = sum(1 for item in items if predicate(item))
        return {
            "passed": passed,
            "total": len(items),
            "rate": None if not items else round(passed / len(items), 4),
        }

    citations = [citation for item in outcomes for citation in item.citations]
    traceable = sum(
        1
        for citation in citations
        if citation.get("file_name") and str(citation["file_name"]).endswith(".md")
    )
    quote_backed = sum(1 for citation in citations if str(citation.get("quote") or ""))
    per_case: dict[str, dict[str, int]] = {}
    for item in outcomes:
        bucket = per_case.setdefault(item.case_id, {"runs": 0, "success": 0, "success_strict": 0})
        bucket["runs"] += 1
        bucket["success"] += int(bool(item.task_success))
        bucket["success_strict"] += int(bool(item.task_success_strict))
    by_scenario: dict[str, dict[str, object]] = {}
    for scenario in sorted({item.scenario for item in outcomes}):
        group = [item for item in outcomes if item.scenario == scenario]
        by_scenario[scenario] = {
            "task_success": rate(group, lambda i: bool(i.task_success)),
            "task_success_strict": rate(group, lambda i: bool(i.task_success_strict)),
            "search_called": rate(group, lambda i: bool(i.searches)),
            "errors": sum(1 for item in group if item.error is not None),
        }
    return {
        "runs": len(outcomes),
        "agent_task_success": rate(history, lambda i: bool(i.task_success)),
        "agent_task_success_strict": rate(history, lambda i: bool(i.task_success_strict)),
        "history_search_call_rate": rate(history, lambda i: bool(i.searches)),
        "plain_chat_search_call_rate": rate(plain, lambda i: bool(i.searches)),
        "plain_chat_no_draft": rate(plain, lambda i: i.draft is None),
        "history_unanswerable_correct": rate(
            [item for item in outcomes if item.scenario == "history_unanswerable"],
            lambda i: bool(i.task_success),
        ),
        "retrieval_sufficient": rate(
            [item for item in outcomes if item.checks.get("retrieval_sufficient") is not None],
            lambda i: i.checks.get("retrieval_sufficient") is True,
        ),
        "recovered_by_read": rate(history, lambda i: i.checks.get("recovered_by_read") is True),
        "citation_traceable": {
            "passed": traceable,
            "total": len(citations),
            "rate": None if not citations else round(traceable / len(citations), 4),
        },
        "citation_quote_backed": {
            "passed": quote_backed,
            "total": len(citations),
            "rate": None if not citations else round(quote_backed / len(citations), 4),
        },
        "by_scenario": by_scenario,
        "per_case": per_case,
        "errors": {f"{item.case_id}-r{item.repeat_index}": item.error for item in outcomes if item.error is not None},
    }


def run_agent_eval(
    *,
    corpus_dir: Path,
    cases_path: Path,
    queries_path: Path,
    split: str,
    variant: str,
    run_id: str,
    var_root: Path,
    results_root: Path,
    prompt_path: Path,
    repeats: int = DEFAULT_REPEATS,
    only_ids: list[str] | None = None,
) -> dict:
    """Run every case in the split ``repeats`` times and write local + committed reports."""
    from noteagent.llm.factory import create_chat_model
    from noteagent.rag_eval.dataset import load_agent_cases, load_corpus, load_queries

    corpus = load_corpus(corpus_dir)
    queries_list = load_queries(queries_path, corpus)
    queries = {query.id: query for query in queries_list}
    cases = [case for case in load_agent_cases(cases_path, queries_list) if case.split == split]
    if only_ids:
        unknown = [item for item in only_ids if item not in {case.id for case in cases}]
        if unknown:
            raise ValueError(f"unknown case ids for split={split}: {unknown}")
        cases = [case for case in cases if case.id in only_ids]
    if not cases:
        raise ValueError(f"no agent cases with split={split!r} in {cases_path}")
    settings = Settings()
    model = create_chat_model(settings)
    run_dir = var_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    outcomes: list[CaseOutcome] = []
    for case in cases:
        for repeat in range(1, repeats + 1):
            case_dir = run_dir / "cases" / f"{case.id}-r{repeat}"
            case_dir.mkdir(parents=True, exist_ok=True)
            try:
                outcome = asyncio.run(
                    run_case(
                        case,
                        repeat_index=repeat,
                        case_dir=case_dir,
                        corpus=corpus,
                        queries=queries,
                        model=model,
                        settings=settings,
                        prompt_path=prompt_path,
                    )
                )
            except Exception as exc:  # noqa: BLE001 - 一次运行失败不能中断整批，也不能算通过
                _logger.exception("agent case aborted id=%s repeat=%d", case.id, repeat)
                outcome = CaseOutcome(
                    case_id=case.id,
                    split=case.split,
                    scenario=case.scenario,
                    repeat_index=repeat,
                    error=f"{type(exc).__name__}: {exc}",
                    task_success=False,
                    task_success_strict=False,
                )
            outcomes.append(outcome)

    summary = summarize(outcomes)
    summary["run_id"] = run_id
    summary["variant"] = variant
    summary["split"] = split
    summary["repeats"] = repeats
    summary["started_at"] = datetime.now(timezone.utc).isoformat()
    _write_agent_outputs(
        run_dir=run_dir, results_root=results_root, run_id=run_id, summary=summary, outcomes=outcomes
    )
    return summary


def _write_agent_outputs(
    *,
    run_dir: Path,
    results_root: Path,
    run_id: str,
    summary: dict,
    outcomes: list[CaseOutcome],
) -> None:
    """Full local JSONL plus a body-free summary the repo can keep."""
    with (run_dir / "results.jsonl").open("w", encoding="utf-8") as handle:
        for item in outcomes:
            payload = asdict(item)
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    (run_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (run_dir / "report.md").write_text(_render_agent_report(summary, outcomes, with_bodies=True), encoding="utf-8")
    committed = results_root / run_id
    committed.mkdir(parents=True, exist_ok=True)
    (committed / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (committed / "summary.md").write_text(
        _render_agent_report(summary, outcomes, with_bodies=False), encoding="utf-8"
    )
    _logger.info("agent run written run_dir=%s committed=%s", run_dir, committed)


def _render_agent_report(summary: dict, outcomes: list[CaseOutcome], *, with_bodies: bool) -> str:
    """Markdown report; ``with_bodies`` keeps model answers and quotes local only."""
    lines = [
        f"# Agent eval {summary['run_id']}",
        "",
        f"- variant: `{summary['variant']}` split: `{summary['split']}` repeats: {summary['repeats']}",
        f"- runs: {summary['runs']}",
        "",
        "## Metrics",
        "",
        "| metric | passed/total | rate |",
        "|---|---|---|",
        f"| Agent 任务成功率（历史场景） | {summary['agent_task_success']['passed']}/"
        f"{summary['agent_task_success']['total']} | {summary['agent_task_success']['rate']} |",
        f"| Agent 任务成功率（严格引用口径） | {summary['agent_task_success_strict']['passed']}/"
        f"{summary['agent_task_success_strict']['total']} | {summary['agent_task_success_strict']['rate']} |",
        f"| 历史任务检索调用率 | {summary['history_search_call_rate']['passed']}/"
        f"{summary['history_search_call_rate']['total']} | {summary['history_search_call_rate']['rate']} |",
        f"| 无需检索误调用率 | {summary['plain_chat_search_call_rate']['passed']}/"
        f"{summary['plain_chat_search_call_rate']['total']} | {summary['plain_chat_search_call_rate']['rate']} |",
        f"| 普通对话不写盘 | {summary['plain_chat_no_draft']['passed']}/"
        f"{summary['plain_chat_no_draft']['total']} | {summary['plain_chat_no_draft']['rate']} |",
        f"| 历史无答案正确处理率 | {summary['history_unanswerable_correct']['passed']}/"
        f"{summary['history_unanswerable_correct']['total']} | {summary['history_unanswerable_correct']['rate']} |",
        f"| 检索片段覆盖必需证据 | {summary['retrieval_sufficient']['passed']}/"
        f"{summary['retrieval_sufficient']['total']} | {summary['retrieval_sufficient']['rate']} |",
        f"| 靠 read_file 兜回正确笔记 | {summary['recovered_by_read']['passed']}/"
        f"{summary['recovered_by_read']['total']} | {summary['recovered_by_read']['rate']} |",
        f"| 引用可定位到文件 | {summary['citation_traceable']['passed']}/"
        f"{summary['citation_traceable']['total']} | {summary['citation_traceable']['rate']} |",
        f"| 引用带回引文（可到章节/原文） | {summary['citation_quote_backed']['passed']}/"
        f"{summary['citation_quote_backed']['total']} | {summary['citation_quote_backed']['rate']} |",
        "",
        "## By scenario",
        "",
        "| scenario | task success | strict | search called | errors |",
        "|---|---|---|---|---|",
    ]
    for scenario, stats in summary["by_scenario"].items():
        lines.append(
            f"| {scenario} | {stats['task_success']['passed']}/{stats['task_success']['total']} "
            f"| {stats['task_success_strict']['passed']}/{stats['task_success_strict']['total']} "
            f"| {stats['search_called']['passed']}/{stats['search_called']['total']} "
            f"| {stats['errors']} |"
        )
    lines += [
        "",
        "## Per case (逐次成功分布)",
        "",
        "| case | runs | success | strict |",
        "|---|---|---|---|",
    ]
    for case_id, stats in sorted(summary["per_case"].items()):
        lines.append(
            f"| {case_id} | {stats['runs']} | {stats['success']} | {stats['success_strict']} |"
        )
    lines += ["", "## Per run checks", ""]
    for item in outcomes:
        failed = [key for key, value in item.checks.items() if value is False]
        lines.append(
            f"- `{item.case_id}` r{item.repeat_index} success={item.task_success} "
            f"tools={item.tools} failed={failed or 'none'}"
            + (f" error={item.error}" if item.error else "")
        )
    if with_bodies:
        lines += ["", "## Model answers (local only)", ""]
        for item in outcomes:
            lines.append(f"### {item.case_id} r{item.repeat_index}")
            lines.append("")
            lines.append(f"- search queries: {[record.query for record in item.searches]}")
            lines.append(f"- citations: {json.dumps(item.citations, ensure_ascii=False)}")
            lines.append(f"- draft: {json.dumps(item.draft, ensure_ascii=False)}")
            lines.append("")
            lines.append("```text")
            lines.append(item.final_answer or "(no answer)")
            lines.append("```")
            lines.append("")
    else:
        lines += [
            "",
            "> 模型回答、检索片段与草稿正文只保存在本地 `var/evals/rag/<run-id>/`（隐私语料）。",
        ]
    return "\n".join(lines)
