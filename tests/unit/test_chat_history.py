import uuid

import pytest
from sqlalchemy import func, select

from noteagent.chat.history import ConversationStore, conversation_title_from_question
from noteagent.db import (
    Base,
    Conversation,
    Message,
    create_engine_from_url,
    create_session_factory,
)


@pytest.fixture
def store() -> ConversationStore:
    engine = create_engine_from_url("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return ConversationStore(create_session_factory(engine))


# ---- title helper ----


def test_title_collapses_whitespace():
    assert conversation_title_from_question("  a   b  ") == "a b"


def test_title_empty_defaults():
    assert conversation_title_from_question("") == "新对话"
    assert conversation_title_from_question("   ") == "新对话"


def test_title_truncates_to_40():
    assert conversation_title_from_question("x" * 40) == "x" * 40
    assert conversation_title_from_question("x" * 100) == "x" * 40


# ---- create / get ----


def test_create_then_get(store: ConversationStore):
    record = store.create("my title")
    fetched = store.get(record.id)
    assert fetched is not None
    assert fetched.id == record.id
    assert fetched.title == "my title"
    assert fetched.created_at is not None
    assert fetched.updated_at is not None


def test_get_unknown_id_returns_none(store: ConversationStore):
    assert store.get("00000000-0000-0000-0000-000000000001") is None


# ---- list conversations ----


def test_list_empty(store: ConversationStore):
    assert store.list_conversations() == []


def test_list_orders_newest_first(store: ConversationStore):
    a = store.create("A")
    b = store.create("B")
    assert [r.id for r in store.list_conversations()] == [b.id, a.id]


# ---- messages ----


def test_append_and_list_messages_order(store: ConversationStore):
    record = store.create("t")
    store.append_message(record.id, "user", "hi")
    store.append_message(record.id, "assistant", "hello")
    messages = store.list_messages(record.id)
    assert messages is not None
    assert [m.role for m in messages] == ["user", "assistant"]
    assert [m.content for m in messages] == ["hi", "hello"]


def test_list_messages_unknown_id_returns_none(store: ConversationStore):
    assert store.list_messages("00000000-0000-0000-0000-000000000001") is None


def test_append_message_unknown_id_raises(store: ConversationStore):
    with pytest.raises(KeyError):
        store.append_message("00000000-0000-0000-0000-000000000001", "user", "x")


def test_append_message_invalid_role(store: ConversationStore):
    record = store.create("t")
    with pytest.raises(ValueError):
        store.append_message(record.id, "system", "x")


def test_cascade_delete_removes_messages(store: ConversationStore):
    record = store.create("t")
    store.append_message(record.id, "user", "hi")
    with store._session_factory() as session:
        conversation = session.get(Conversation, uuid.UUID(record.id))
        session.delete(conversation)
        session.commit()
    with store._session_factory() as session:
        count = session.scalar(select(func.count()).select_from(Message))
    assert count == 0


# ---- rename / delete ----


def test_rename_updates_title(store: ConversationStore):
    record = store.create("old")
    renamed = store.rename(record.id, "  new   title  ")
    assert renamed.title == "new title"
    assert store.get(record.id).title == "new title"


def test_rename_keeps_list_order(store: ConversationStore):
    a = store.create("A")
    b = store.create("B")
    store.rename(a.id, "A2")
    assert [r.id for r in store.list_conversations()] == [b.id, a.id]


def test_rename_unknown_id_raises(store: ConversationStore):
    with pytest.raises(KeyError):
        store.rename("00000000-0000-0000-0000-000000000001", "x")


def test_rename_blank_title_raises(store: ConversationStore):
    record = store.create("t")
    with pytest.raises(ValueError):
        store.rename(record.id, "   ")


def test_rename_too_long_raises(store: ConversationStore):
    record = store.create("t")
    with pytest.raises(ValueError):
        store.rename(record.id, "x" * 81)


def test_delete_removes_conversation_and_messages(store: ConversationStore):
    record = store.create("t")
    store.append_message(record.id, "user", "hi")
    store.delete(record.id)
    assert store.get(record.id) is None
    assert store.list_messages(record.id) is None
    with store._session_factory() as session:
        count = session.scalar(select(func.count()).select_from(Message))
    assert count == 0


def test_delete_unknown_id_raises(store: ConversationStore):
    with pytest.raises(KeyError):
        store.delete("00000000-0000-0000-0000-000000000001")
