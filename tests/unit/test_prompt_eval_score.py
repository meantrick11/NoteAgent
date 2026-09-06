"""L1 v0.1 scorer: headings, invented titles, anchors, H1, behavior gate."""

from pathlib import Path

from noteagent.prompt_eval.cases import load_cases
from noteagent.prompt_eval.score import score_note

_CASES = Path(__file__).resolve().parents[2] / "evals" / "prompt" / "cases.jsonl"

_N01_BODY = """## 2. 使用 Python 的解释器

在可用的机器上 Python 解释器通常被安装为 /usr/local/bin/python3.14。

### 2.1. 唤出解释器

键入 python3.14 即可启动。另一种启动方式是 python -c command。模块可当作脚本：python -m module。

#### 2.1.1. 传入参数

参数在 sys.argv。执行 import sys 可访问。

#### 2.1.2. 交互模式

主提示符通常为 >>>，次要提示符为 ...。

### 2.2. 解释器的运行环境

#### 2.2.1. 源文件的字符编码

默认 UTF-8。
"""


def _n01():
    return load_cases(_CASES, ["n01"])[0]


def _metric(score, metric_id: str):
    return next(item for item in score.metrics if item.metric_id == metric_id)


def test_n01_headings_score_high_structure():
    case = _n01()
    result = score_note(
        case,
        proposed=True,
        tools=["list_files", "propose_note"],
        action="create",
        file_name="Python.md",
        content=_N01_BODY,
    )
    assert result.behavior_pass is True
    assert result.total is not None
    assert _metric(result, "structure.heading_recall").score == 10
    assert _metric(result, "structure.heading_precision").score == 10
    assert _metric(result, "structure.heading_level").score == 10
    assert _metric(result, "structure.h1").score == 10
    assert result.parents["structure"] == 100.0
    assert result.parents["fluent"] is None


def test_invented_heading_precision_zero():
    case = _n01()
    body = _N01_BODY + "\n## 其他启动方式\n\n用别的办法启动。\n"
    result = score_note(
        case,
        proposed=True,
        tools=["list_files"],
        action="create",
        file_name="Python.md",
        content=body,
    )
    assert _metric(result, "structure.heading_precision").score == 0


def test_missing_anchors_score_zero():
    case = _n01()
    body = """## 2. 使用 Python 的解释器

### 2.1. 唤出解释器

解释器可以启动。

#### 2.1.1. 传入参数

参数在列表里。

#### 2.1.2. 交互模式

交互运行。

### 2.2. 解释器的运行环境

#### 2.2.1. 源文件的字符编码

默认编码。
"""
    result = score_note(
        case,
        proposed=True,
        tools=["list_files"],
        action="create",
        file_name="Python.md",
        content=body,
    )
    assert _metric(result, "complete.anchors").score == 0


def test_create_h1_in_body_scores_zero():
    case = _n01()
    result = score_note(
        case,
        proposed=True,
        tools=["list_files"],
        action="create",
        file_name="Python.md",
        content="# 解释器\n\n" + _N01_BODY,
    )
    assert _metric(result, "structure.h1").score == 0


def test_behavior_fail_does_not_score_body():
    case = _n01()
    result = score_note(
        case,
        proposed=False,
        tools=[],
        action=None,
        file_name=None,
        content=None,
    )
    assert result.behavior_pass is False
    assert result.total is None
    assert result.parents["faithful"] is None
    assert result.metrics == []
