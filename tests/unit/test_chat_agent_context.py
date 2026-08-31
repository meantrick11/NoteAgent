from pathlib import Path

from langchain_core.messages import AIMessage, ToolMessage

from noteagent.chat.agent import ChatAgent
from noteagent.chat.context_budget import ContextBudget
from noteagent.chat.context_tokens import estimate_tokens
from noteagent.chat.drafts import DraftStore
from noteagent.chat.history import ConversationStore, start_turn
from noteagent.chat.tools import build_chat_tools
from noteagent.db import Base, create_engine_from_url, create_session_factory
from noteagent.notes.repository import FileNoteRepository


def _budget(stub_preview_tokens: int = 2) -> ContextBudget:
    return ContextBudget(
        window=32768, trigger_ratio=0.8, target_ratio=0.6,
        stub_preview_tokens=stub_preview_tokens, args_preview_chars=500,
        output_reserve=1024, safety_buffer=512,
    )


class _FakeRetrieval:
    def search(self, query: str, top_k: int = 3):
        return []


class ScriptedModel:
    """Fake model: bind_tools returns self; astream pops a scripted reply."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.seen = []

    def bind_tools(self, tools):
        return self

    async def astream(self, messages, config=None):
        self.seen.append(messages)
        yield self.replies.pop(0)

    def invoke(self, messages):
        return AIMessage(content="SUMCHUNK")


def _agent(
    tmp_path: Path,
    model: ScriptedModel,
    stub_preview_tokens: int = 2,
    budget: ContextBudget | None = None,
):
    notes = FileNoteRepository(tmp_path)
    engine = create_engine_from_url("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    history = ConversationStore(create_session_factory(engine))
    drafts = DraftStore()
    tools = build_chat_tools(notes, _FakeRetrieval(), drafts)
    agent = ChatAgent(
        model=model, tools=tools, notes=notes, drafts=drafts,
        history=history,
        budget=budget or _budget(stub_preview_tokens),
    )
    return agent, history, notes


async def _consume(agen):
    return [item async for item in agen]


async def test_stream_writes_stub_and_ui_hides_tool(tmp_path: Path):
    model = ScriptedModel([
        AIMessage(content="", tool_calls=[{"name": "list_files", "id": "c1", "args": {}}]),
        AIMessage(content="done"),
    ])
    agent, history, _notes = _agent(tmp_path, model)

    conv = history.create("t")
    turn = start_turn()
    history.append_message(conv.id, "user", "hi", turn_id=turn)

    await _consume(agent.stream("hi", conv.id, turn))

    pers = history.list_persistent_after_watermark(conv.id)
    tool_rows = [r for r in pers if r.role == "tool"]
    assert len(tool_rows) == 1
    assert estimate_tokens(tool_rows[0].output_preview) <= _budget().stub_preview_tokens

    history.append_message(conv.id, "assistant", "done", turn_id=turn)
    ui = history.list_messages(conv.id)
    assert [r.role for r in ui] == ["user", "assistant"]


async def test_second_turn_does_not_see_previous_tool_full(tmp_path: Path):
    model = ScriptedModel([
        AIMessage(content="", tool_calls=[{"name": "read_file", "id": "c1", "args": {"file_name": "A.md"}}]),
        AIMessage(content="first done"),
        AIMessage(content="second done"),
    ])
    agent, history, notes = _agent(tmp_path, model, stub_preview_tokens=10)

    notes.create("A.md", "A")
    notes.write("A.md", "X" * 1000 + "UNIQUE_TAIL_MARKER", append=True)

    conv = history.create("t")
    turn1 = start_turn()
    history.append_message(conv.id, "user", "q1", turn_id=turn1)
    await _consume(agent.stream("q1", conv.id, turn1))
    history.append_message(conv.id, "assistant", "first done", turn_id=turn1)

    turn2 = start_turn()
    history.append_message(conv.id, "user", "q2", turn_id=turn2)
    await _consume(agent.stream("q2", conv.id, turn2))

    # Turn 1 internal hop saw the full ToolMessage.
    internal = "\n".join(
        str(m.content) for m in model.seen[1] if isinstance(m.content, str)
    )
    assert "UNIQUE_TAIL_MARKER" in internal

    # Turn 2 first hop must not carry the previous turn's full ToolMessage.
    second = model.seen[2]
    assert not any(isinstance(m, ToolMessage) for m in second)
    second_text = "\n".join(str(m.content) for m in second if isinstance(m.content, str))
    assert "UNIQUE_TAIL_MARKER" not in second_text
    assert "[tool_stub]" in second_text
    assert any("q1" in str(m.content) for m in second if isinstance(m.content, str))


async def test_runtime_tool_message_has_name(tmp_path: Path):
    model = ScriptedModel([
        AIMessage(content="", tool_calls=[{"name": "list_files", "id": "c1", "args": {}}]),
        AIMessage(content="done"),
    ])
    agent, history, _notes = _agent(tmp_path, model)
    conv = history.create("t")
    turn = start_turn()
    history.append_message(conv.id, "user", "hi", turn_id=turn)
    await _consume(agent.stream("hi", conv.id, turn))

    tools = [m for m in model.seen[1] if isinstance(m, ToolMessage)]
    assert len(tools) == 1
    assert tools[0].name == "list_files"
    assert tools[0].tool_call_id == "c1"


async def test_two_tools_in_one_turn_second_hop_sees_first_full(tmp_path: Path):
    model = ScriptedModel([
        AIMessage(content="", tool_calls=[{"name": "read_file", "id": "c1", "args": {"file_name": "A.md"}}]),
        AIMessage(content="", tool_calls=[{"name": "list_files", "id": "c2", "args": {}}]),
        AIMessage(content="done"),
    ])
    agent, history, notes = _agent(tmp_path, model, stub_preview_tokens=2)
    notes.create("A.md", "A")
    notes.write("A.md", "UNIQUE_FULL_BODY", append=True)
    conv = history.create("t")
    turn = start_turn()
    history.append_message(conv.id, "user", "q", turn_id=turn)
    await _consume(agent.stream("q", conv.id, turn))

    hop2 = model.seen[1]
    assert any(
        isinstance(m, ToolMessage) and "UNIQUE_FULL_BODY" in str(m.content) and m.name == "read_file"
        for m in hop2
    )


async def test_max_tool_hops_stops_loop(tmp_path: Path):
    replies = [
        AIMessage(content="", tool_calls=[{"name": "list_files", "id": f"c{i}", "args": {}}])
        for i in range(10)
    ]
    model = ScriptedModel(replies)
    limited = ContextBudget(
        window=32768, trigger_ratio=0.8, target_ratio=0.6,
        stub_preview_tokens=2, args_preview_chars=500,
        output_reserve=1024, safety_buffer=512,
        max_tool_hops=2,
    )
    agent, history, _notes = _agent(tmp_path, model, budget=limited)
    conv = history.create("t")
    turn = start_turn()
    history.append_message(conv.id, "user", "hi", turn_id=turn)
    await _consume(agent.stream("hi", conv.id, turn))
    stubs = [r for r in history.list_persistent_after_watermark(conv.id) if r.role == "tool"]
    assert len(stubs) == 2


async def test_tiny_window_compacts_older_complete_turn(tmp_path: Path):
    """Shrink W so pack >= 80%W; drop the older completed turn, keep UI bubbles."""
    tiny = ContextBudget(
        window=80, trigger_ratio=0.8, target_ratio=0.6,
        stub_preview_tokens=10, args_preview_chars=50,
        output_reserve=1, safety_buffer=1,
    )
    model = ScriptedModel([AIMessage(content="turn3-ok")])
    agent, history, _notes = _agent(tmp_path, model, budget=tiny)

    conv = history.create("t")
    t1, t2, t3 = start_turn(), start_turn(), start_turn()
    history.append_message(conv.id, "user", "u1 UNIQUE_TURN1", turn_id=t1)
    history.append_message(conv.id, "assistant", "a1 " + ("Z" * 200), turn_id=t1)
    history.append_message(conv.id, "user", "u2 UNIQUE_TURN2", turn_id=t2)
    history.append_message(conv.id, "assistant", "a2 " + ("Y" * 200), turn_id=t2)
    history.append_message(conv.id, "user", "u3", turn_id=t3)

    await _consume(agent.stream("u3", conv.id, t3))

    rec = history.get(conv.id)
    assert rec.summary_watermark_turn_id == t1
    assert rec.running_summary and "SUMCHUNK" in rec.running_summary

    tail = history.list_persistent_after_watermark(conv.id)
    assert not any("UNIQUE_TURN1" in (r.content or "") for r in tail)
    assert any("UNIQUE_TURN2" in (r.content or "") for r in tail)

    ui = history.list_messages(conv.id)
    assert any("UNIQUE_TURN1" in r.content for r in ui)
