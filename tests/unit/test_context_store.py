import uuid

import pytest

from noteagent.chat.context_tokens import estimate_tokens
from noteagent.chat.history import ConversationStore, start_turn
from noteagent.db import Base, Conversation, Message, create_engine_from_url, create_session_factory


@pytest.fixture
def store() -> ConversationStore:
    engine = create_engine_from_url("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return ConversationStore(create_session_factory(engine))


def test_models_have_context_columns():
    engine = create_engine_from_url("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    assert "running_summary" in Conversation.__table__.c
    assert "summary_watermark_turn_id" in Conversation.__table__.c
    assert "turn_id" in Message.__table__.c
    assert "tool_name" in Message.__table__.c
    assert "tool_arguments" in Message.__table__.c
    assert "output_preview" in Message.__table__.c
    assert "truncated" in Message.__table__.c
    assert "status" in Message.__table__.c


def test_append_requires_turn_id(store: ConversationStore):
    c = store.create("t")
    tid = start_turn()
    m = store.append_message(c.id, "user", "hi", turn_id=tid)
    assert m.turn_id == tid
    assert m.role == "user"


def test_list_messages_hides_tool_stubs(store: ConversationStore):
    c = store.create("t")
    tid = start_turn()
    store.append_message(c.id, "user", "hi", turn_id=tid)
    store.append_tool_stub(
        c.id, turn_id=tid, tool_name="read_file",
        arguments='{"file_name":"A.md"}', output="x" * 200,
        status="ok", stub_preview_tokens=2, args_preview_chars=500,
    )
    store.append_message(c.id, "assistant", "done", turn_id=tid)
    ui = store.list_messages(c.id)
    assert [x.role for x in ui] == ["user", "assistant"]
    pers = store.list_persistent_after_watermark(c.id)
    assert [x.role for x in pers] == ["user", "tool", "assistant"]
    stub = pers[1]
    assert stub.truncated is True
    assert estimate_tokens(stub.output_preview) <= 2


def test_tool_stub_does_not_bump_updated_at(store: ConversationStore):
    c = store.create("t")
    tid = start_turn()
    store.append_message(c.id, "user", "hi", turn_id=tid)
    before = store.get(c.id).updated_at
    store.append_tool_stub(
        c.id, turn_id=tid, tool_name="read_file",
        arguments="{}", output="x" * 200,
        status="ok", stub_preview_tokens=2, args_preview_chars=500,
    )
    after = store.get(c.id).updated_at
    assert after == before


def test_watermark_hides_summarized_turns(store: ConversationStore):
    c = store.create("t")
    t1, t2 = start_turn(), start_turn()
    store.append_message(c.id, "user", "u1", turn_id=t1)
    store.append_message(c.id, "assistant", "a1", turn_id=t1)
    store.append_message(c.id, "user", "u2", turn_id=t2)
    store.append_message(c.id, "assistant", "a2", turn_id=t2)
    store.apply_compact(c.id, summary_append="old talk", watermark_turn_id=t1)
    tail = store.list_persistent_after_watermark(c.id)
    assert [x.content for x in tail] == ["u2", "a2"]
    rec = store.get(c.id)
    assert rec.running_summary == "old talk"
    assert rec.summary_watermark_turn_id == t1
    store.apply_compact(c.id, summary_append="newer", watermark_turn_id=t2)
    assert store.get(c.id).running_summary == "old talk\n\nnewer"


def test_null_turn_id_watermark_still_hides_summarized_turn(store: ConversationStore):
    c = store.create("t")
    t1, t2 = start_turn(), start_turn()
    store.append_message(c.id, "user", "u1", turn_id=t1)
    store.append_message(c.id, "assistant", "a1", turn_id=t1)
    with store._session_factory() as session:
        session.add(
            Message(
                conversation_id=uuid.UUID(c.id),
                role="assistant",
                content="orphan-no-turn",
                turn_id=None,
            )
        )
        session.commit()
    store.append_message(c.id, "user", "u2", turn_id=t2)
    store.append_message(c.id, "assistant", "a2", turn_id=t2)
    store.apply_compact(c.id, summary_append="old talk", watermark_turn_id=t1)
    tail = [x.content for x in store.list_persistent_after_watermark(c.id)]
    assert "u1" not in tail and "a1" not in tail
    assert "u2" in tail and "a2" in tail
    assert "orphan-no-turn" in tail


def test_append_message_rejects_tool_role(store: ConversationStore):
    c = store.create("t")
    with pytest.raises(ValueError):
        store.append_message(c.id, "tool", "x", turn_id=start_turn())
