"""The URL reader flows through the real graph and checkpoint, per requirement REQ-009.

The scripted model issues ``read_webpage`` calls; the assertions check what the next
model hop sees, what the intermediate checkpoint keeps, and that a finished turn
leaves no active runtime text behind.
"""

from __future__ import annotations

import uuid

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from NoteAgent.BusinessModules.ChatAgent.ChatExecution import execute_turn
from NoteAgent.BusinessModules.ChatAgent.ChatGraph import build_chat_graph
from NoteAgent.BusinessModules.ChatAgent.WebReading import WebPageResult
from NoteAgent.BusinessModules.ConversationState.ConversationModels import ConversationRun
from NoteAgent.BusinessModules.ConversationState.ConversationCheckpoints import thread_config
from Support.Fakes import FakeWebReader

BODY = "网页正文内容ABC"


def _ok(url: str) -> WebPageResult:
    return WebPageResult(url=url, final_url=url, status="ok", title="标题", content=BODY, error=None)


def _failed(url: str) -> WebPageResult:
    return WebPageResult(url=url, final_url=None, status="failed", title=None, content="", error="请求超时")


def _tool_calls(*urls: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {"name": "read_webpage", "id": f"w{i}", "args": {"url": url}}
            for i, url in enumerate(urls)
        ],
    )


async def test_two_urls_one_success_one_failure_through_checkpoint(conversation_harness):
    h = conversation_harness
    h.web_reader = FakeWebReader({"https://a.test/ok": _ok("https://a.test/ok"), "https://a.test/bad": _failed("https://a.test/bad")})
    c = await h.create_conversation()
    h.model.replies = [
        _tool_calls("https://a.test/ok", "https://a.test/bad"),
        AIMessage(content="第一篇讲…，第二篇读取失败。"),
    ]

    await h.complete_turn(c.id, "看这两个：https://a.test/ok https://a.test/bad")

    assert h.web_reader.calls == ["https://a.test/ok", "https://a.test/bad"]

    # The follow-up hop sees the full success body and the failure status.
    tool_msgs = [m for m in h.model.calls[-1] if isinstance(m, ToolMessage)]
    assert any(BODY in m.content for m in tool_msgs)
    failed = [m for m in tool_msgs if '"failed"' in m.content]
    assert failed and "请求超时" in failed[0].content
    assert not any(BODY in m.content for m in failed)

    view = await h.service.get_state(c.id)
    assistant = [m for m in view.values["ui_messages"] if m.get("role") == "assistant"][-1]
    web_steps = [s for s in assistant["tool_steps"] if s["name"] == "read_webpage"]
    assert {s["status"] for s in web_steps} == {"ok", "error"}
    assert {s["web_status"] for s in web_steps} == {"ok", "failed"}
    assert all(BODY not in s["preview"] for s in web_steps)

    # The active turn runtime is cleared once the turn finishes.
    assert view.values["runtime_messages"] == []

    # Another conversation never sees this page's body.
    other = await h.create_conversation()
    h.model.replies = [AIMessage(content="无关回答")]
    await h.complete_turn(other.id, "另一个问题")
    assert not any(BODY in (getattr(m, "content", "") or "") for m in h.model.calls[-1])


async def test_interrupted_web_turn_keeps_body_in_middle_checkpoint(conversation_harness):
    h = conversation_harness
    h.web_reader = FakeWebReader({"https://a.test/ok": _ok("https://a.test/ok")})
    c = await h.create_conversation()
    h.model.replies = [_tool_calls("https://a.test/ok")]

    prepared = await h.service.prepare_turn(c.id, "读一下 https://a.test/ok", "web-interrupt")
    graph = build_chat_graph(h.graph_runtime(), h.runtime.saver)
    with pytest.raises(AssertionError, match="ran out of scripted replies"):
        async for _ in execute_turn(graph, h.service, prepared):
            pass

    with h.service._session_factory() as session:
        run = session.get(ConversationRun, uuid.UUID(prepared.run_id))
        assert run.status == "interrupted"
        checkpoint = run.checkpoint_id
    state = await h.service.read_state(thread_config(c.id, checkpoint))
    mid_tools = [m for m in state.values["runtime_messages"] if isinstance(m, ToolMessage)]
    assert any(BODY in m.content for m in mid_tools)

    h.model.replies = [AIMessage(content="好的，已读。")]
    resumed = h.service.resume_turn(prepared.run_id)
    async for _ in execute_turn(graph, h.service, resumed, resume=True):
        pass

    view = await h.service.get_state(c.id)
    assert view.values["runtime_messages"] == []
    messages = await h.service.list_messages(c.id)
    assert [m.content for m in messages] == ["读一下 https://a.test/ok", "好的，已读。"]


async def test_graph_binds_read_webpage_with_per_url_instruction(conversation_harness):
    """The scripted model must be offered the tool, with the per-URL rule in its schema."""
    h = conversation_harness
    h.web_reader = FakeWebReader({"https://a.test/ok": _ok("https://a.test/ok")})
    c = await h.create_conversation()
    h.model.replies = [AIMessage(content="好的")]

    await h.complete_turn(c.id, "你好")

    bound = {t.name: t for t in h.model.bound_tools}
    assert "read_webpage" in bound
    assert "逐个" in (bound["read_webpage"].description or "")


async def test_no_reader_means_no_tool_bound(conversation_harness):
    h = conversation_harness
    c = await h.create_conversation()
    h.model.replies = [AIMessage(content="好的")]

    await h.complete_turn(c.id, "你好")

    assert "read_webpage" not in {t.name for t in h.model.bound_tools}
