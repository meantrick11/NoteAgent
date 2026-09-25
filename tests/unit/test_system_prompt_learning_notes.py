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
_V10_PROMPT = _PROMPTS / "iterations" / "v10-2026-09-25-conflict-before-replace.txt"


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


def test_explicit_fidelity_mode_uses_first_six_rules_only():
    """Literal fidelity must not fail the learning-only processing rule."""
    prompt = _prompt()

    assert "学习型笔记必须满足七条质量标准" in prompt
    assert "完全忠实翻译、逐段翻译或保持原结构时，满足前六条" in prompt
    assert "第 7 条“知识加工增益”不适用" in prompt
    assert "不能因逐段忠实而否决" in prompt


def test_quality_rules_define_semantic_fidelity_and_completeness():
    """The hard gates constrain claims and coverage rather than surface form."""
    prompt = _prompt()

    assert "事实、模态、条件、例外和关键语义单元" in prompt
    assert "不得补充外部背景事实" in prompt
    assert "不按字数或句数" in prompt
    for unit in ("独立论点", "步骤", "例证", "专名", "限定/例外", "关系"):
        assert unit in prompt
    assert "不得漏掉当前用户任务范围内任何章节信息" in prompt
    assert "不得把无关章节混成错误结论" in prompt


def test_completeness_and_structure_are_limited_to_current_task_scope():
    """A requested excerpt must not inherit coverage duties from other sections."""
    prompt = _prompt()
    completeness = next(line for line in prompt.splitlines() if line.startswith("2. 完整"))
    structure = next(line for line in prompt.splitlines() if line.startswith("3. 结构"))

    assert "当前用户任务范围内" in completeness
    assert "当前用户任务范围内" in structure
    assert "局部摘录或只保留某节" in prompt
    assert "不要求覆盖任务范围外的标题" in prompt
    assert "普通学习型笔记可在不遗漏当前用户任务范围内各节信息" in prompt
    assert "普通学习型笔记可在不遗漏各节信息" not in prompt


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


def test_example_contrasts_literal_translation_with_tradeoff_grouping():
    """The example must demonstrate source-backed semantic processing."""
    prompt = _prompt()

    assert "学习型反例（逐句照译）" in prompt
    assert "学习型正例（按“方案取舍”组织）" in prompt
    assert "## 方案取舍" in prompt
    assert "Shell 适合移动文件和修改文本数据，却不适合 GUI 应用或游戏" in prompt
    assert "C/C++/Java 即使第一版程序也可能耗时" in prompt
    assert "相比之下，Python 更易用，并能跨 Windows、macOS 和 Unix 运行" in prompt


def test_latest_prompt_archive_is_byte_identical_to_production_prompt():
    """入库约定：**最新一版**归档必须与现行 system.txt 字节一致；旧档不再改动。"""
    assert _V10_PROMPT.read_bytes() == _SYSTEM_PROMPT.read_bytes()


def test_older_prompt_archives_are_kept():
    """旧归档保持可追溯：v9 仍在，且与 v10 不同（说明确实改过）。"""
    assert _V9_PROMPT.is_file()
    assert _V9_PROMPT.read_bytes() != _V10_PROMPT.read_bytes()
