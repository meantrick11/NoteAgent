"""L1 v0.1 scorer: headings, invented titles, anchors, H1, behavior gate."""

from pathlib import Path

from noteagent.prompt_eval.cases import load_cases
from noteagent.prompt_eval.score import _extract_literals, _literals, score_note

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


def test_extract_literals_path_wrappers_and_punctuation():
    """Paths after (, \", or before !/? extract the same /usr/bin literal."""
    assert _extract_literals("run (/usr/bin) now") == ["/usr/bin"]
    assert _extract_literals('see "/usr/bin" here') == ["/usr/bin"]
    assert _extract_literals("use /usr/bin!") == ["/usr/bin"]
    assert _extract_literals("The binary lives at /usr/bin.") == ["/usr/bin"]


def test_extract_literals_skips_io_and_keeps_rich_paths():
    """I/O is not a path; versions, +/@/~/%/= and Unicode segments stay intact."""
    assert _extract_literals("file I/O, system calls") == []
    text = (
        "/usr/local/bin/python3.14 /srv/app+blue /srv/x@y "
        "/srv/a~b /srv/p%q /srv/r=s /用户/文档"
    )
    assert _extract_literals(text) == [
        "/usr/local/bin/python3.14",
        "/srv/app+blue",
        "/srv/x@y",
        "/srv/a~b",
        "/srv/p%q",
        "/srv/r=s",
        "/用户/文档",
        "python3.14",
    ]


def test_extract_literals_path_case_is_preserved():
    """Unix path matching is case-sensitive; fixed identifiers still lower-case."""
    upper = _extract_literals("Deploy to /srv/App and python3.14")
    lower = _extract_literals("Deploy to /srv/app and python3.14")
    assert upper == ["/srv/App", "python3.14"]
    assert lower == ["/srv/app", "python3.14"]
    assert set(upper) != set(lower)


def test_literals_path_case_sensitive():
    """Draft must not swap /srv/App for /srv/app without scoring extra."""
    material = "Deploy to /srv/App."
    result = _literals(material, "部署到 /srv/app。")
    assert result.score == 0
    assert any("/srv/app" in item for item in result.raw.get("extra", []))


def test_literals_io_slash_not_treated_as_path():
    """English I/O must not make /O a spurious absolute-path literal."""
    material = (
        "Some modules provide file I/O, system calls, sockets, "
        "and even GUI toolkits like Tk."
    )
    content = "其中一些模块提供文件 I/O、系统调用、套接字（sockets）。"
    result = _literals(material, content)
    assert result.metric_id == "faithful.literals"
    assert result.score == 10
    extra = result.raw.get("extra", [])
    assert not any("/O" in item or "系统调用" in item or "套接字" in item for item in extra)


def test_literals_unix_absolute_path_still_detected():
    """Real Unix paths like /usr/local/bin/python3.14 must still be tracked."""
    material = "Python is usually installed as /usr/local/bin/python3.14 on Unix."
    faithful = _literals(material, "解释器通常安装为 /usr/local/bin/python3.14 on Unix.")
    assert faithful.score == 10
    assert "/usr/local/bin/python3.14" in faithful.raw["source"]
    assert "/usr/local/bin/python3.14" in faithful.raw["draft"]

    invented = _literals(material, "解释器在 /usr/local/bin/python3.99 on Unix.")
    assert invented.score == 0
    assert any("python3.99" in item for item in invented.raw["extra"])


def test_literals_path_plus_variants_are_distinguishable():
    """Paths with + must not be truncated; blue vs green must differ."""
    material = "Deploy to /srv/app+blue or /srv/app+green."
    faithful = _literals(material, "部署到 /srv/app+blue 或 /srv/app+green。")
    assert faithful.score == 10
    assert "/srv/app+blue" in faithful.raw["source"]
    assert "/srv/app+green" in faithful.raw["source"]

    invented = _literals(material, "部署到 /srv/app+blue 或 /srv/app+red。")
    assert invented.score == 0
    extra = invented.raw.get("extra", [])
    assert any("app+red" in item for item in extra)
    assert not any("app+green" in item for item in extra)


def test_literals_trailing_period_matches_bare_path():
    """Sentence-ending period after a path must not make it a different literal."""
    material = "The binary lives at /usr/bin."
    content = "可执行文件位于 /usr/bin。"
    result = _literals(material, content)
    assert result.score == 10
    assert "/usr/bin" in result.raw["source"]
    assert "/usr/bin" in result.raw["draft"]
    assert "/usr/bin." not in result.raw["source"]


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
