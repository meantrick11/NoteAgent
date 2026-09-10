"""Contract tests for the learning-note calibration dataset."""

import re
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


def test_learning_notes_source_keeps_representative_original_passages():
    """The l01 source retains representative sentences from every major section."""
    source = load_cases(_LEARNING_CASES, ["l01"])[0].user
    passages = [
        "If you do much work on computers, eventually you find that there’s some task you’d like to automate.",
        "the high-level data types allow you to express complex operations in a single statement",
        "statement grouping is done by indentation instead of beginning and ending brackets",
        "no variable or argument declarations are necessary",
        "Python is extensible: if you know how to program in C",
        "the language is named after the BBC show “Monty Python’s Flying Circus”",
        "The rest of the tutorial introduces various features of the Python language and system through examples",
    ]

    assert all(passage in source for passage in passages)


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


def test_good_fixture_is_faithful_and_covers_core_contract():
    """The good candidate preserves core concepts and source-backed relations."""
    good = (_FIXTURES / "good.md").read_text(encoding="utf-8")
    core_evidence = [
        "Shell 脚本最擅长移动文件和修改文本数据，却不适合 GUI 应用或游戏",
        "C/C++/Java",
        "第一版程序",
        "Python 更容易使用",
        "Windows、macOS 和 Unix",
        "模块",
        "标准模块",
        "不需要编译和链接",
        "高级数据类型可用一条语句表达复杂操作",
        "把 Python 解释器嵌入 C 应用",
        "Monty Python’s Flying Circus",
        "异常和用户自定义类",
    ]

    assert "不值得重新设计" not in good
    assert "不想为应用设计和实现一门全新语言" in good
    assert "Python 同样容易使用" not in good
    assert all(evidence in good for evidence in core_evidence)


def test_literal_fixture_keeps_only_source_heading_and_paragraph_sequence():
    """The literal candidate stays a paragraph-by-paragraph translation."""
    literal = (_FIXTURES / "literal.md").read_text(encoding="utf-8")
    headings = re.findall(r"^#{1,6} .+$", literal, flags=re.MULTILINE)
    paragraphs = [block for block in literal.split("\n\n") if not block.startswith("#")]

    assert headings == ["## 1. 激发你的兴趣"]
    assert len(paragraphs) >= 12
    assert paragraphs[0].startswith("如果你经常使用计算机")
    assert paragraphs[-1].startswith("教程其余部分")


def test_omitted_fixture_excludes_a_declared_must_concept():
    """The omitted candidate demonstrably drops the C-extension concept."""
    case = load_cases(_LEARNING_CASES, ["l01"])[0]
    omitted = (_FIXTURES / "omitted.md").read_text(encoding="utf-8")

    assert any(concept.startswith("用 C 添加内建函数") for concept in case.must_concepts)
    assert "内建函数或模块" not in omitted
    assert "嵌入 C 应用" not in omitted


def test_hallucinated_fixture_contains_a_forbidden_claim():
    """The hallucinated candidate contains a claim forbidden by l01."""
    case = load_cases(_LEARNING_CASES, ["l01"])[0]
    hallucinated = (_FIXTURES / "hallucinated.md").read_text(encoding="utf-8")

    assert any(claim in hallucinated for claim in case.forbidden_claims)


@pytest.mark.parametrize(
    "name",
    ["good.md", "literal.md", "omitted.md", "hallucinated.md"],
)
def test_learning_note_fixture_is_utf8_readable(name: str):
    """Each fixed candidate exists and contains readable UTF-8 Markdown."""
    content = (_FIXTURES / name).read_text(encoding="utf-8")

    assert content.strip()
    assert "\ufffd" not in content
