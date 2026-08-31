from datetime import datetime, timezone

from noteagent.chat.context_budget import ContextBudget
from noteagent.chat.context_tokens import estimate_tokens
from noteagent.chat.context_compact import (
    TurnBundle,
    compute_f,
    concat_summary,
    group_turns,
    select_turns_to_drop,
    should_compact,
)
from noteagent.chat.history import MessageRecord


def _rec(turn, role, content, idx=0):
    return MessageRecord(
        id=f"id-{idx}", conversation_id="c", role=role, content=content,
        created_at=datetime.now(timezone.utc), turn_id=turn,
        tool_name=None, tool_arguments=None, output_preview=None,
        truncated=False, status=None,
    )


def _budget(**over) -> ContextBudget:
    defaults = dict(
        window=100, trigger_ratio=0.8, target_ratio=0.6,
        stub_preview_tokens=1000, args_preview_chars=500,
        output_reserve=1024, safety_buffer=512,
    )
    defaults.update(over)
    return ContextBudget(**defaults)


def _bundle(turn_id, tokens, complete=True):
    return TurnBundle(turn_id=turn_id, records=[], tokens=tokens, complete=complete)


def test_group_turns_order_and_complete():
    records = [
        _rec("t1", "user", "u1", 1),
        _rec("t1", "assistant", "a1", 2),
        _rec("t2", "user", "u2", 3),
        _rec("t2", "assistant", "a2", 4),
    ]
    bundles = group_turns(records)
    assert [b.turn_id for b in bundles] == ["t1", "t2"]
    assert [b.complete for b in bundles] == [True, True]


def test_group_turns_incomplete_without_assistant():
    bundles = group_turns([_rec("t1", "user", "u1", 1)])
    assert bundles[0].complete is False


def test_select_drops_oldest_complete():
    bundles = [
        _bundle("t1", 10),
        _bundle("t2", 20),
        _bundle("t3", 30),
        _bundle("cur", 999),
    ]
    drop, keep = select_turns_to_drop(bundles, current_turn_id="cur", k_tokens=35)
    assert [b.turn_id for b in drop] == ["t1", "t2"]
    assert [b.turn_id for b in keep] == ["t3", "cur"]


def test_select_keeps_single_oversized_complete():
    bundles = [_bundle("big", 100), _bundle("cur", 10)]
    drop, keep = select_turns_to_drop(bundles, current_turn_id="cur", k_tokens=5)
    assert [b.turn_id for b in drop] == []
    assert [b.turn_id for b in keep] == ["big", "cur"]


def test_current_turn_never_dropped():
    bundles = [_bundle("t1", 10), _bundle("t2", 20), _bundle("cur", 999, complete=False)]
    drop, keep = select_turns_to_drop(bundles, current_turn_id="cur", k_tokens=5)
    assert [b.turn_id for b in drop] == ["t1"]
    assert [b.turn_id for b in keep] == ["t2", "cur"]


def test_concat_summary():
    assert concat_summary(None, "x") == "x"
    assert concat_summary("", "x") == "x"
    assert concat_summary("a", "b") == "a\n\nb"


def test_should_compact_threshold():
    assert should_compact(80, _budget()) is True
    assert should_compact(79, _budget()) is False


def test_compute_f_includes_reserves():
    budget = _budget()
    f = compute_f(
        system="", tool_defs="", summary="", current_user="",
        draft_line=None, runtime="", budget=budget,
    )
    assert f == budget.output_reserve + budget.safety_buffer
    f2 = compute_f(
        system="abcd", tool_defs="", summary="", current_user="",
        draft_line=None, runtime="", budget=budget,
    )
    assert f2 == budget.output_reserve + budget.safety_buffer + 1


def test_tool_stub_tokens_counted_once():
    preview = "abcd"
    rec = MessageRecord(
        id="id-1", conversation_id="c", role="tool", content=preview,
        created_at=datetime.now(timezone.utc), turn_id="t1",
        tool_name="read_file", tool_arguments="{}", output_preview=preview,
        truncated=False, status="ok",
    )
    expected = (
        estimate_tokens("read_file")
        + estimate_tokens("{}")
        + estimate_tokens(preview)
    )
    assert group_turns([rec])[0].tokens == expected


def test_null_turn_complete_is_not_dropped():
    orphan = _rec(None, "assistant", "legacy", 1)
    current = _rec("cur", "user", "now", 2)
    drop, keep = select_turns_to_drop(
        group_turns([orphan, current]), current_turn_id="cur", k_tokens=1
    )
    assert drop == []
    assert any(b.records and b.records[0].id == "id-1" for b in keep)
