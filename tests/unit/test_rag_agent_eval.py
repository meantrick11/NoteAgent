"""Offline unit tests for the Agent-layer RAG evaluator. No model, no API, no Chroma."""

from pathlib import Path

from noteagent.rag_eval.agent_run import (
    CaseOutcome,
    RecordingRetrieval,
    attach_searches,
    SearchRecord,
    _citation_intervals,
    _read_before_propose,
    _task_success,
    evaluate_checks,
    summarize,
)
from noteagent.rag_eval.dataset import (
    AgentCase,
    Corpus,
    EvidenceLocation,
    EvidenceUnit,
    NoteRecord,
    QueryCase,
)
from noteagent.rag_eval.metrics import Interval
from noteagent.retrieval.models import SearchHit

NOTE_TEXT = "# Alpha\n\n## 第一节\n\n回溯是递归的副产品。\n"
QUOTE = "回溯是递归的副产品。"


def _corpus() -> Corpus:
    record = NoteRecord(
        note_id="Alpha",
        file="Alpha.md",
        sha256="x",
        origin_path="notes/Alpha.md",
        source_file=None,
        source_status="missing",
        review_status="provisional",
        issues=(),
    )
    return Corpus(
        root=Path("corpus"),
        notes={"Alpha": record},
        texts={"Alpha": NOTE_TEXT},
        headings={"Alpha": ()},
    )


def _query() -> QueryCase:
    start = NOTE_TEXT.index(QUOTE)
    return QueryCase(
        id="q01",
        group_id="g1",
        split="dev",
        query="回溯和递归什么关系？",
        category="fact",
        answerable=True,
        evidence_units=(
            EvidenceUnit(
                id="u1",
                fact="回溯是递归的副产品",
                alternatives=(
                    EvidenceLocation(
                        note_id="Alpha",
                        heading_path="Alpha > 第一节",
                        start_char=start,
                        end_char=start + len(QUOTE),
                        quote=QUOTE,
                    ),
                ),
            ),
        ),
    )


def _case(**overrides) -> AgentCase:
    base = dict(
        id="a01",
        group_id="ga",
        split="dev",
        scenario="history_answer",
        user="问",
        pre_dialogue=(),
        expect_search=True,
        expect_action=None,
        target_file=None,
        new_content=None,
        evidence_refs=("q01",),
        must_preserve_refs=(),
        must_not_contain_refs=(),
        expect_flags_conflict=False,
        conflict_markers=(),
        expect_no_write=True,
        notes="",
    )
    base.update(overrides)
    return AgentCase(**base)


def _outcome(**overrides) -> CaseOutcome:
    base = dict(case_id="a01", split="dev", scenario="history_answer", repeat_index=1)
    base.update(overrides)
    return CaseOutcome(**base)


def test_citation_intervals_counts_read_citations_as_the_whole_note():
    corpus = _corpus()
    outcome = _outcome(
        citations=[
            {"file_name": "Alpha.md", "chunk_index": 0, "quote": QUOTE},
            {"file_name": "Alpha.md", "chunk_index": None, "quote": None},
            {"file_name": "Ghost.md", "chunk_index": 0, "quote": QUOTE},
            {"file_name": "Alpha.md", "chunk_index": 0, "quote": "不存在的引用"},
        ]
    )
    start = NOTE_TEXT.index(QUOTE)
    assert _citation_intervals(outcome, corpus) == [
        Interval("Alpha", start, start + len(QUOTE)),
        Interval("Alpha", 0, len(NOTE_TEXT)),
    ]
    # 严格口径只认带回引文、能定位到原文的引用。
    assert _citation_intervals(outcome, corpus, quote_backed_only=True) == [
        Interval("Alpha", start, start + len(QUOTE))
    ]


def test_history_answer_needs_a_citation_covering_the_evidence():
    corpus = _corpus()
    queries = {"q01": _query()}
    case = _case()

    cited = _outcome(citations=[{"file_name": "Alpha.md", "chunk_index": 0, "quote": QUOTE}])
    checks = evaluate_checks(case, cited, queries=queries, notes=None, corpus=corpus)
    assert checks["evidence_cited"] is True

    uncited = _outcome(citations=[])
    checks = evaluate_checks(case, uncited, queries=queries, notes=None, corpus=corpus)
    assert checks["evidence_cited"] is False


def test_read_before_propose_is_required_for_the_target_file():
    case = _case(scenario="history_append", expect_action="append", target_file="Alpha.md")
    good = _outcome(
        tools=["list_files", "search_relative_from_chromadb", "read_file", "propose_note"],
        tool_arguments=["{}", "{}", '{"file_name": "Alpha.md"}', "{}"],
        draft={"action": "append", "file_name": "Alpha.md"},
    )
    assert _read_before_propose(case, good) is True
    unread = _outcome(
        tools=["propose_note"],
        tool_arguments=["{}"],
        draft={"action": "append", "file_name": "Alpha.md"},
    )
    assert _read_before_propose(case, unread) is False
    wrong_file = _outcome(
        tools=["read_file", "propose_note"],
        tool_arguments=['{"file_name": "Beta.md"}', "{}"],
        draft={"action": "append", "file_name": "Alpha.md"},
    )
    assert _read_before_propose(case, wrong_file) is False


def test_duplicate_case_accepts_explaining_instead_of_writing():
    queries = {"q01": _query()}
    case = _case(
        scenario="history_append",
        target_file="Alpha.md",
        expect_action="append",
        must_not_contain_refs=("q01",),
    )
    explained = _outcome(
        scenario="history_append",
        final_answer="这条内容笔记里已经有了，无需重复记录。",
        draft=None,
        checks={"search_called": True, "no_draft_explained": True},
    )
    assert _task_success(case, explained) is True

    silent = _outcome(
        scenario="history_append",
        final_answer="好的。",
        draft=None,
        checks={"search_called": True, "no_draft_explained": False},
    )
    assert _task_success(case, silent) is False


def test_duplicate_check_reads_the_draft_content():
    corpus = _corpus()
    queries = {"q01": _query()}
    case = _case(
        scenario="history_append",
        target_file="Alpha.md",
        expect_action="append",
        must_not_contain_refs=("q01",),
    )
    duplicated = _outcome(
        scenario="history_append",
        draft={"action": "append", "file_name": "Alpha.md", "content": f"补充：{QUOTE}"},
    )
    checks = evaluate_checks(case, duplicated, queries=queries, notes=None, corpus=corpus)
    assert checks["must_not_contain"] is False

    fresh = _outcome(
        scenario="history_append",
        draft={"action": "append", "file_name": "Alpha.md", "content": "全新的内容。"},
    )
    checks = evaluate_checks(case, fresh, queries=queries, notes=None, corpus=corpus)
    assert checks["must_not_contain"] is True


def test_a_draft_that_never_reached_disk_is_not_a_pass():
    corpus = _corpus()
    queries = {"q01": _query()}
    case = _case(
        scenario="history_append",
        target_file="Alpha.md",
        expect_action="append",
        must_preserve_refs=("q01",),
    )
    not_committed = _outcome(
        scenario="history_append",
        draft={"action": "append", "file_name": "Alpha.md", "content": "新内容。"},
        committed=False,
        checks={
            "search_called": True,
            "action_ok": True,
            "target_ok": True,
            "append_needs_read": True,
            "draft_applied": False,
            "must_preserve": None,
            "must_not_contain": None,
        },
    )
    assert _task_success(case, not_committed) is False


def test_conflict_case_fails_when_the_clash_is_not_flagged():
    case = _case(
        scenario="history_append",
        target_file="Alpha.md",
        expect_action="append",
        expect_flags_conflict=True,
        conflict_markers=("矛盾",),
    )
    flagged = _outcome(
        scenario="history_append",
        draft={"action": "append", "file_name": "Alpha.md"},
        checks={
            "search_called": True,
            "action_ok": True,
            "target_ok": True,
            "append_needs_read": True,
            "must_preserve": True,
            "must_not_contain": None,
            "flags_conflict": True,
        },
    )
    assert _task_success(case, flagged) is True

    silent = _outcome(
        scenario="history_append",
        draft={"action": "append", "file_name": "Alpha.md"},
        checks={**flagged.checks, "flags_conflict": False},
    )
    assert _task_success(case, silent) is False


def test_unanswerable_case_requires_a_stated_gap_and_no_draft():
    case = _case(scenario="history_unanswerable", evidence_refs=(), expect_no_write=True)
    stated = _outcome(
        scenario="history_unanswerable",
        final_answer="我的笔记里没有找到相关记录。",
        checks={"search_called": True, "states_no_evidence": True},
    )
    assert _task_success(case, stated) is True
    invented = _outcome(
        scenario="history_unanswerable",
        final_answer="根据笔记，GIL 会让多线程无法并行。",
        checks={"search_called": True, "states_no_evidence": False},
    )
    assert _task_success(case, invented) is False


def test_plain_chat_success_needs_no_search_and_no_draft():
    case = _case(scenario="plain_chat", evidence_refs=(), expect_search=False)
    assert _task_success(case, _outcome(scenario="plain_chat")) is True
    overzealous = _outcome(
        scenario="plain_chat",
        searches=[SearchRecord(query="x", top_k=3, hits=[])],
    )
    assert _task_success(case, overzealous) is False


def test_recording_retrieval_records_the_query_and_hits():
    class _Inner:
        def search(self, query, top_k=3):
            return [SearchHit(content="片段", distance=0.4, metadata={"file_name": "Alpha.md", "chunk_index": 0})]

    recorder = RecordingRetrieval(_Inner(), {"Alpha": (["片段"], [Interval("Alpha", 0, 2)])}, _corpus())
    recorder.search("问题", top_k=3)
    assert recorder.searches[0].query == "问题"
    assert recorder.searches[0].hits[0].note_id == "Alpha"
    assert recorder.searches[0].hits[0].start_char == 0


def test_attach_searches_flags_a_harness_mismatch():
    class _Inner:
        def search(self, query, top_k=3):
            return []

    recorder = RecordingRetrieval(_Inner(), {}, _corpus())
    matched = _outcome(
        tools=["search_relative_from_chromadb"],
        searches=None,
    )
    matched.searches = []
    recorder.searches = [SearchRecord(query="q", top_k=3, hits=[])]
    attach_searches(matched, recorder)
    assert matched.searches == recorder.searches
    assert matched.error is None

    mismatched = _outcome(tools=["search_relative_from_chromadb", "read_file"])
    attach_searches(mismatched, RecordingRetrieval(_Inner(), {}, _corpus()))
    assert mismatched.searches == []
    assert "harness" in (mismatched.error or "")


def test_attach_tool_stubs_prefers_the_persisted_arguments():
    from noteagent.chat.history import ConversationStore, start_turn
    from noteagent.db import Base, create_engine_from_url, create_session_factory

    from noteagent.rag_eval.agent_run import attach_tool_stubs

    engine = create_engine_from_url("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    history = ConversationStore(create_session_factory(engine))
    conv = history.create("t")
    turn = start_turn()
    history.append_tool_stub(
        conv.id,
        turn_id=turn,
        tool_name="read_file",
        arguments='{"file_name": "Alpha.md"}',
        output="{}",
        status="ok",
        stub_preview_tokens=100,
        args_preview_chars=100,
    )
    outcome = _outcome(tools=["read_file"])
    attach_tool_stubs(outcome, history, conv.id)
    assert outcome.tools == ["read_file"]
    assert '"Alpha.md"' in outcome.tool_arguments[0]
    assert outcome.error is None

    orphan = _outcome(tools=["read_file"])
    empty = history.create("empty")
    attach_tool_stubs(orphan, history, empty.id)
    assert "harness" in (orphan.error or "")


def test_summarize_reports_counts_and_keeps_plain_chat_out_of_success():
    outcomes = [
        _outcome(
            case_id="a01",
            task_success=True,
            task_success_strict=True,
            searches=[SearchRecord("q", 3, [])],
        ),
        _outcome(case_id="a02", task_success=False, searches=[]),
        _outcome(case_id="a11", scenario="plain_chat", task_success=True),
    ]
    summary = summarize(outcomes)
    assert summary["agent_task_success"] == {"passed": 1, "total": 2, "rate": 0.5}
    assert summary["history_search_call_rate"] == {"passed": 1, "total": 2, "rate": 0.5}
    assert summary["plain_chat_search_call_rate"] == {"passed": 0, "total": 1, "rate": 0.0}
    assert summary["per_case"]["a01"] == {"runs": 1, "success": 1, "success_strict": 1}
