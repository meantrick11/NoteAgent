"""Focused contracts for the v9 learning-note generation prompt."""

import re
from pathlib import Path


_PROMPTS = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "noteagent"
    / "chat"
    / "prompts"
)
_SYSTEM_PROMPT = _PROMPTS / "system.txt"
_V9_PROMPT = _PROMPTS / "iterations" / "v9-2026-09-10-learning-notes.txt"


def _prompt() -> str:
    """Read the production prompt exactly as the agent does."""
    return _SYSTEM_PROMPT.read_text(encoding="utf-8")


def test_default_note_mode_is_learning_note_not_literal_translation():
    """A plain note request must select semantic organization by default."""
    prompt = _prompt()

    assert "默认“记下来/整理成笔记”是学习型笔记" in prompt
    assert "普通“翻译并整理为笔记”仍是中文学习型笔记" in prompt
    assert "允许合并重复、调整句序、按语义分组" in prompt
    assert "增加有正文依据的子标题" in prompt


def test_original_structure_requires_an_explicit_fidelity_request():
    """Only explicit fidelity wording may make source structure the skeleton."""
    prompt = _prompt()

    assert "完全忠实翻译" in prompt
    assert "逐段翻译" in prompt
    assert "保持原结构" in prompt
    assert "才以原结构为输出骨架" in prompt
    assert "标题应翻译且编号可保留" in prompt


def test_quality_rules_define_semantic_fidelity_and_completeness():
    """The hard gates constrain claims and coverage rather than surface form."""
    prompt = _prompt()

    assert "事实、模态、条件、例外和关键语义单元" in prompt
    assert "不得补充外部背景事实" in prompt
    assert "不按字数或句数" in prompt
    for unit in ("独立论点", "步骤", "例证", "专名", "限定/例外", "关系"):
        assert unit in prompt
    assert "不得漏掉任何章节信息" in prompt
    assert "不得把无关章节混成错误结论" in prompt


def test_constraint_has_seven_rules_with_processing_gain_last():
    """The quality contract must expose processing gain as rule seven."""
    prompt = _prompt()
    rule_numbers = re.findall(r"(?m)^([1-7])\. ", prompt)

    assert rule_numbers == [str(number) for number in range(1, 8)]
    assert "七条质量标准" in prompt
    assert "7. 知识加工增益" in prompt
    assert "事实、命令、代码可贴近原文" in prompt
    assert "说理、背景、动机、比较" in prompt
    assert "禁止零加工逐句转写" in prompt
    assert "禁止为了改写而改写" in prompt


def test_v9_archive_is_byte_identical_to_production_prompt():
    """The immutable v9 archive must capture the exact released prompt."""
    assert _V9_PROMPT.read_bytes() == _SYSTEM_PROMPT.read_bytes()
