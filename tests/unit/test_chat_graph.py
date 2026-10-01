"""The chat graph persists per-node state and keeps display history intact."""

from langchain_core.messages import AIMessage


def script(harness, *replies) -> None:
    """Queue the model's replies for the next hops (one entry per model call)."""
    harness.model.replies = [
        reply if isinstance(reply, AIMessage) else AIMessage(content=str(reply))
        for reply in replies
    ]


def events_of(events, name: str) -> list[dict]:
    return [item for item in events if item.get("event") == name]


async def test_single_hop_turn_records_user_and_assistant(conversation_harness):
    h = conversation_harness
    conversation = await h.create_conversation()
    script(h, "你好")
    events = await h.complete_turn(conversation.id, "问题")

    messages = await h.service.list_messages(conversation.id)
    assert [m.role for m in messages] == ["user", "assistant"]
    assert messages[0].content == "问题"
    assert messages[1].content == "你好"

    assert events_of(events, "thinking")
    assert events_of(events, "token")
    assert events_of(events, "assistant_final")[0]["data"] == "你好"

    state = await h.service.get_state(conversation.id)
    assert state.values["run_status"] == "completed"
    assert state.values["runtime_messages"] == []
    assert state.values["tool_steps"] == []
    # the user message was written once, by preparation, not by a node
    assert len(state.values["ui_messages"]) == 2


async def test_tool_hop_keeps_pairing_and_hides_hop_prose(conversation_harness):
    h = conversation_harness
    conversation = await h.create_conversation()
    h.notes.create("A.md", "A")
    script(
        h,
        AIMessage(
            content="先查一下",
            tool_calls=[{"name": "list_files", "id": "c1", "args": {}}],
        ),
        "完成",
    )
    events = await h.complete_turn(conversation.id, "列出文件")

    # tool-hop prose is trace-only; the answer bubble holds the final hop only
    assert [item["data"] for item in events_of(events, "think")] == ["先查一下"]
    assert events_of(events, "assistant_final")[0]["data"] == "完成"
    tool_events = events_of(events, "tool")
    assert tool_events and tool_events[0]["data"]["name"] == "list_files"
    assert events_of(events, "tool_done")[0]["data"]["status"] == "ok"

    state = await h.service.get_state(conversation.id)
    assert [m["role"] for m in state.values["ui_messages"]] == ["user", "assistant"]
    assistant = state.values["ui_messages"][1]
    assert assistant["tool_steps"][0]["name"] == "list_files"
    assert state.values["run_status"] == "completed"


async def test_hop_limit_stops_the_loop_and_never_fakes_success(conversation_harness):
    h = conversation_harness
    conversation = await h.create_conversation()
    # budget allows 3 hops; supply tool calls beyond that
    script(
        h,
        *[
            AIMessage(
                content="",
                tool_calls=[{"name": "list_files", "id": f"c{i}", "args": {}}],
            )
            for i in range(3)
        ],
    )
    events = await h.complete_turn(conversation.id, "无限工具")

    state = await h.service.get_state(conversation.id)
    assert state.values["run_status"] == "failed"
    assert events_of(events, "assistant_final") == []
    # the user bubble is still there; the failure did not erase history
    assert state.values["ui_messages"][0]["content"] == "无限工具"


async def test_compaction_keeps_display_history(conversation_harness):
    """Compaction shrinks the model window, never the display history."""
    h = conversation_harness
    conversation = await h.create_conversation()
    script(h, "答1")
    await h.complete_turn(conversation.id, "第一条需要保留的材料")
    script(h, "答2")
    await h.complete_turn(conversation.id, "第二条材料")
    script(h, "答3")
    await h.complete_turn(conversation.id, "第三条材料", force_compact=True)

    state = await h.service.get_state(conversation.id)
    displayed = await h.service.list_messages(conversation.id)

    assert displayed[0].content == "第一条需要保留的材料"
    assert state.values["running_summary"]
    assert h.summaries, "the summarizer must have run"
    assert len(state.values["working_records"]) < len(state.values["ui_messages"])


async def test_draft_survives_the_turn_in_state(conversation_harness):
    h = conversation_harness
    conversation = await h.create_conversation()
    h.notes.create("A.md", "A")
    script(
        h,
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "propose_note",
                    "id": "p1",
                    "args": {
                        "action": "append",
                        "file_name": "A.md",
                        "content": "新增内容",
                    },
                }
            ],
        ),
        "已提案",
    )
    events = await h.complete_turn(conversation.id, "追加内容")

    draft_events = events_of(events, "draft")
    assert draft_events and draft_events[0]["data"]["file_name"] == "A.md"
    state = await h.service.get_state(conversation.id)
    assert state.values["pending_draft"]["content"] == "新增内容"
    # proposing never writes the note itself
    assert "新增内容" not in h.notes.read("A.md")


async def test_prepare_turn_is_single_claim_per_request(conversation_harness):
    h = conversation_harness
    conversation = await h.create_conversation()
    from noteagent.conversations.service import TurnAlreadyClaimed

    await h.service.prepare_turn(conversation.id, "问题", request_id="req-1")
    try:
        await h.service.prepare_turn(conversation.id, "问题", request_id="req-1")
    except TurnAlreadyClaimed:
        pass
    else:  # pragma: no cover - the duplicate must be rejected
        raise AssertionError("duplicate request_id must not prepare a second turn")
