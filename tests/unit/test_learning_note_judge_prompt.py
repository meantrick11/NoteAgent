"""Focused contracts for the learning-note Judge prompt evidence rules."""

from pathlib import Path


_PROMPT = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "noteagent"
    / "prompt_eval"
    / "prompts"
    / "learning_note_judge.txt"
)


def _prompt() -> str:
    """Read the Judge prompt exactly as judge_learning_note does."""
    return _PROMPT.read_text(encoding="utf-8")


def test_evidence_source_must_be_verbatim_from_request_task():
    """Source evidence must name request.task and require verbatim continuous copies."""
    prompt = _prompt()

    assert "request.task" in prompt
    assert "evidence" in prompt and "source" in prompt
    assert "原样逐字复制" in prompt
    assert "连续" in prompt


def test_evidence_draft_must_be_verbatim_from_draft_content():
    """Draft evidence must name draft.content and require verbatim continuous copies."""
    prompt = _prompt()

    assert "draft.content" in prompt
    assert "evidence" in prompt and "draft" in prompt
    assert prompt.count("原样逐字复制") >= 2


def test_retrievable_draft_may_cite_draft_file_name():
    """Only retrievable draft evidence may copy draft.file_name verbatim."""
    prompt = _prompt()

    assert "draft.file_name" in prompt
    assert "retrievable" in prompt


def test_review_question_draft_evidence_only_from_draft_content():
    """Review-question evidence must be verbatim draft.content, not file names."""
    prompt = _prompt()

    assert "draft_evidence" in prompt
    assert "draft.content" in prompt
    assert "draft.file_name" in prompt
    assert "复习" in prompt or "review_questions" in prompt


def test_evidence_forbids_translation_paraphrase_and_fragment_splicing():
    """Judge must forbid summarizing, rewriting, ellipsis, and non-contiguous joins."""
    prompt = _prompt()

    for phrase in ("禁止翻译", "改写", "省略号", "拼接"):
        assert phrase in prompt


def test_json_escape_must_not_change_decoded_evidence():
    """JSON escaping must preserve decoded evidence strings for substring checks."""
    prompt = _prompt()

    assert "JSON" in prompt
    assert "转义" in prompt
    assert "解码" in prompt


def test_missing_evidence_still_cites_closest_fragments_without_fabrication():
    """Failures must cite nearest real fragments; absence is explained, never invented."""
    prompt = _prompt()

    assert "最接近" in prompt
    assert "不得伪造" in prompt
    assert "reason" in prompt
