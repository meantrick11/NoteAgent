"""Contract tests for the learning-note calibration dataset."""

from pathlib import Path

import pytest

from noteagent.prompt_eval.cases import load_cases


_ROOT = Path(__file__).resolve().parents[2]
_LEARNING_CASES = _ROOT / "evals" / "prompt" / "learning_notes.jsonl"
_LEGACY_CASES = _ROOT / "evals" / "prompt" / "cases.jsonl"
_FIXTURES = _ROOT / "evals" / "prompt" / "fixtures" / "learning_notes"


def test_learning_notes_case_loads_semantic_contract():
    """The main calibration case exposes every v0.2 semantic field."""
    cases = load_cases(_LEARNING_CASES)

    assert len(cases) == 1
    case = cases[0]
    assert case.id == "l01"
    assert case.task_mode == "learning_note"
    assert case.output_language == "zh-CN"
    assert case.must_concepts
    assert case.must_relations
    assert case.must_preserve
    assert case.forbidden_claims
    assert case.review_questions
    assert case.quality_thresholds == {
        "structure": 3,
        "fluent": 3,
        "processing": 3,
    }


def test_legacy_cases_keep_empty_semantic_defaults():
    """Existing JSONL rows remain loadable without v0.2 fields."""
    case = load_cases(_LEGACY_CASES, ["n01"])[0]

    assert case.task_mode == ""
    assert case.output_language == ""
    assert case.must_concepts == []
    assert case.must_relations == []
    assert case.must_preserve == []
    assert case.forbidden_claims == []
    assert case.review_questions == []
    assert case.quality_thresholds == {}


@pytest.mark.parametrize(
    "name",
    ["good.md", "literal.md", "omitted.md", "hallucinated.md"],
)
def test_learning_note_fixture_is_utf8_readable(name: str):
    """Each fixed candidate exists and contains readable UTF-8 Markdown."""
    content = (_FIXTURES / name).read_text(encoding="utf-8")

    assert content.strip()
    assert "\ufffd" not in content
