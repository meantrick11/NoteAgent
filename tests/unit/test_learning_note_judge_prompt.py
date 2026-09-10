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

_REVIEW_QUESTION_RULE = (
    "可回答时给出非空 `answer`，并在 `draft_evidence` 中至少放一段从 `draft.content` "
    "原样逐字复制的连续片段；`draft_evidence` 禁止翻译、改写、加省略号、拼接不相邻片段或引用 "
    "`draft.file_name`。"
)

_EVIDENCE_VERBATIM_RULE = (
    "每个硬门和每个维度都必须给出非空的 source、draft 证据数组和 `reason`。"
    "`evidence.*.source` 的每条字符串必须从 `request.task` 原样逐字复制一段连续片段；"
    "`evidence.*.draft` 的每条字符串必须从 `draft.content` 原样逐字复制一段连续片段，"
    "仅 `evidence.retrievable.draft` 还可从 `draft.file_name` 原样逐字复制。"
)

_EVIDENCE_FORBIDDEN_RULE = (
    "禁止翻译、概括、改写、加省略号、拼接不相邻片段，或用 JSON 转义改变解码后的字符。"
)

_EVIDENCE_REASON_RULE = (
    "`reason` 用自然语言解释证据如何支持评分，或说明缺失/冲突；不得用 `reason` 代替 "
    "source 或 draft 证据，也不得伪造输入中不存在的片段。"
)

_EVIDENCE_FAILURE_RULE = (
    "硬门失败或维度低分时，source 引用与判定最相关的来源要求片段，draft 引用最接近的"
    "现有草稿片段，具体缺失或冲突写入 `reason`。"
)

_JSON_EXAMPLE_EVIDENCE = (
    '"task_alignment": {"source": ["..."], "draft": ["..."], "reason": "..."}'
)


def _prompt() -> str:
    """Read the Judge prompt exactly as judge_learning_note does."""
    return _PROMPT.read_text(encoding="utf-8")


def test_review_question_draft_evidence_must_copy_draft_content_only():
    """Review-question evidence must be verbatim draft.content, never draft.file_name."""
    prompt = _prompt()

    assert _REVIEW_QUESTION_RULE in prompt


def test_evidence_source_and_draft_must_be_verbatim_from_named_inputs():
    """Metric evidence must copy request.task and draft.content as continuous fragments."""
    prompt = _prompt()

    assert _EVIDENCE_VERBATIM_RULE in prompt


def test_only_retrievable_draft_may_cite_draft_file_name():
    """Only retrievable draft evidence may copy draft.file_name verbatim."""
    prompt = _prompt()

    assert "仅 `evidence.retrievable.draft` 还可从 `draft.file_name` 原样逐字复制。" in prompt


def test_evidence_forbids_translation_paraphrase_and_fragment_splicing():
    """Judge must forbid summarizing, rewriting, ellipsis, and non-contiguous joins."""
    prompt = _prompt()

    assert _EVIDENCE_FORBIDDEN_RULE in prompt


def test_evidence_reason_explains_without_replacing_substrings():
    """Each metric evidence object must carry a non-empty reason separate from substrings."""
    prompt = _prompt()

    assert _EVIDENCE_REASON_RULE in prompt
    assert _JSON_EXAMPLE_EVIDENCE in prompt


def test_failure_scores_cite_closest_fragments_and_put_gaps_in_reason():
    """Low scores must cite real fragments and explain missing pieces in reason only."""
    prompt = _prompt()

    assert _EVIDENCE_FAILURE_RULE in prompt
