from datetime import datetime, timezone

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from noteagent.chat.context_budget import ContextBudget
from noteagent.chat.context_pack import (
    build_pack,
    draft_workspace_line,
    extract_source_headings,
    records_to_langchain,
    source_heading_tree_line,
    stub_text,
)
from noteagent.chat.drafts import NoteDraft
from noteagent.chat.history import MessageRecord


def _budget() -> ContextBudget:
    return ContextBudget(
        window=32768, trigger_ratio=0.8, target_ratio=0.6,
        stub_preview_tokens=1000, args_preview_chars=500,
        output_reserve=1024, safety_buffer=512,
    )


def _rec(turn, role, content, idx=0, tool_name=None, output_preview=None):
    return MessageRecord(
        id=f"id-{idx}", conversation_id="c", role=role, content=content,
        created_at=datetime.now(timezone.utc), turn_id=turn,
        tool_name=tool_name, tool_arguments=None, output_preview=output_preview,
        truncated=False, status=None,
    )


def test_draft_workspace_line_none():
    assert draft_workspace_line(None) is None


def test_draft_workspace_line_has_action_and_file():
    draft = NoteDraft(action="create", file_name="Go.md", content="## x")
    line = draft_workspace_line(draft)
    assert "create" in line
    assert "Go.md" in line


def test_stub_text_has_name_and_preview():
    record = _rec("t", "tool", "PREVIEW", tool_name="read_file", output_preview="PREVIEW")
    text = stub_text(record)
    assert "name=read_file" in text
    assert "preview=PREVIEW" in text


def test_records_to_langchain_roles():
    records = [
        _rec("t", "user", "hi", 1),
        _rec("t", "assistant", "yo", 2),
        _rec("t", "tool", "P", 3, tool_name="read_file", output_preview="P"),
    ]
    msgs = records_to_langchain(records)
    assert isinstance(msgs[0], HumanMessage)
    assert msgs[2].content == stub_text(records[2])


def test_build_pack_excludes_current_tool_stub_keeps_runtime_full():
    current = "cur"
    user_rec = _rec(current, "user", "question?", idx=1)
    tool_rec = _rec(current, "tool", "PREVIEW", idx=2, tool_name="read_file", output_preview="PREVIEW")
    runtime = [ToolMessage(content="FULL TOOL OUTPUT", tool_call_id="c1")]
    pack = build_pack(
        system_prompt="sys", tool_defs="defs", summary=None,
        persistent=[user_rec, tool_rec], current_turn_id=current,
        current_user="question?", draft_line=None, runtime_messages=runtime,
        budget=_budget(),
    )
    joined = "\n".join(
        m.content for m in pack.messages if isinstance(m.content, str)
    )
    assert "FULL TOOL OUTPUT" in joined
    assert "[tool_stub]" not in joined
    assert "PREVIEW" not in joined


def test_build_pack_base_and_runtime_cost():
    budget = _budget()
    base = build_pack(
        system_prompt="sys", tool_defs="defs", summary=None,
        persistent=[], current_turn_id="cur", current_user="hello",
        draft_line=None, runtime_messages=[], budget=budget,
    )
    kinds = [type(m).__name__ for m in base.messages]
    assert "SystemMessage" in kinds
    assert kinds.count("HumanMessage") == 1

    big = build_pack(
        system_prompt="sys", tool_defs="defs", summary=None,
        persistent=[], current_turn_id="cur", current_user="hello",
        draft_line=None,
        runtime_messages=[ToolMessage(content="r" * 4000, tool_call_id="c1")],
        budget=budget,
    )
    assert big.f_tokens - base.f_tokens >= 100


_PYTHON_INTERPRETER_SAMPLE = """
生成一下内容的笔记：
2. 使用 Python 的解释器
2.1. 唤出解释器
在可用的机器上 Python 解释器通常被安装为 /usr/local/bin/python3.14。

python3.14
Python 3.14 (default, April 4 2024, 09:25:04)
[GCC 10.2.0] on linux
>>>
the_world_is_flat = True
if the_world_is_flat:
    print("Be careful not to fall off!")

2.1.1. 传入参数
解释器读取命令行参数。
2.1.2. 交互模式
在终端输入并执行指令时。
2.2. 解释器的运行环境
2.2.1. 源文件的字符编码
默认情况下，Python 源码文件的编码是 UTF-8。
# -*- coding: encoding -*-
#!/usr/bin/env python3
# -*- coding: cp1252 -*-
"""


def test_extract_source_headings_python_tutorial():
    headings = extract_source_headings(_PYTHON_INTERPRETER_SAMPLE)
    assert headings == [
        "2. 使用 Python 的解释器",
        "2.1. 唤出解释器",
        "2.1.1. 传入参数",
        "2.1.2. 交互模式",
        "2.2. 解释器的运行环境",
        "2.2.1. 源文件的字符编码",
    ]
    assert ">>>" not in headings
    assert not any("coding:" in h for h in headings)


def test_extract_source_headings_atx():
    headings = extract_source_headings("## Real section\n### Nested\nbody\n>>>")
    assert headings == ["## Real section", "### Nested"]


def test_source_heading_tree_line_none_for_chat():
    assert source_heading_tree_line("今天天气怎么样") is None


def test_build_pack_injects_heading_tree():
    pack = build_pack(
        system_prompt="sys", tool_defs="defs", summary=None,
        persistent=[], current_turn_id="cur",
        current_user=_PYTHON_INTERPRETER_SAMPLE,
        draft_line=None, runtime_messages=[], budget=_budget(),
    )
    joined = "\n".join(m.content for m in pack.messages if isinstance(m.content, str))
    assert "材料标题树" in joined
    assert "2.1.1. 传入参数" in joined
    assert "禁止合并或另造标题" in joined
