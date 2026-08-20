"""Persistence for chat history: conversations and their messages.

This is the only write path for user-visible history. HTTP handlers call
``ConversationStore``; they never ``session.add`` directly.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from noteagent.db.models import Conversation, Message

_logger = logging.getLogger(__name__)

_ROLES = {"user", "assistant"}


def conversation_title_from_question(question: str, max_len: int = 40) -> str:
    """Collapse whitespace and truncate for the sidebar title."""
    text = " ".join(question.split())
    if not text:
        return "新对话"
    return text if len(text) <= max_len else text[:max_len]


def normalize_conversation_title(title: str, max_len: int = 80) -> str:
    """Collapse whitespace; return "" if nothing left; raise if over max_len."""
    text = " ".join(title.split())
    if len(text) > max_len:
        raise ValueError("title too long")
    return text


@dataclass(slots=True)
class ConversationRecord:
    id: str
    title: str
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class MessageRecord:
    id: str
    conversation_id: str
    role: str
    content: str
    created_at: datetime


class ConversationStore:
    """Persist conversations and messages. One short-lived Session per method."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def create(self, title: str) -> ConversationRecord:
        """Insert a new conversation and return its record."""
        with self._session_factory() as session:
            row = Conversation(title=title)
            session.add(row)
            session.commit()
            _logger.info("created conversation=%s", row.id)
            return _to_conversation(row)

    def get(self, conversation_id: str) -> ConversationRecord | None:
        """Return a conversation by id, or None if missing or malformed."""
        try:
            parsed = uuid.UUID(conversation_id)
        except ValueError:
            return None
        with self._session_factory() as session:
            row = session.get(Conversation, parsed)
            return _to_conversation(row) if row is not None else None

    def list_conversations(self) -> list[ConversationRecord]:
        """Return all conversations ordered by updated_at DESC, created_at DESC."""
        with self._session_factory() as session:
            rows = session.scalars(
                select(Conversation).order_by(
                    Conversation.updated_at.desc(),
                    Conversation.created_at.desc(),
                )
            ).all()
            return [_to_conversation(row) for row in rows]

    def list_messages(self, conversation_id: str) -> list[MessageRecord] | None:
        """Return messages for a conversation, None if missing, [] if empty.

        Messages are ordered created_at ASC, id ASC.
        """
        try:
            parsed = uuid.UUID(conversation_id)
        except ValueError:
            return None
        with self._session_factory() as session:
            if session.get(Conversation, parsed) is None:
                return None
            rows = session.scalars(
                select(Message)
                .where(Message.conversation_id == parsed)
                .order_by(Message.created_at.asc(), Message.id.asc())
            ).all()
            return [_to_message(row) for row in rows]

    def append_message(self, conversation_id: str, role: str, content: str) -> MessageRecord:
        """Insert a message and bump the conversation's updated_at.

        Raises KeyError if the conversation is missing or the id is malformed;
        ValueError if role is not in {user, assistant}.
        """
        if role not in _ROLES:
            raise ValueError(f"invalid role: {role!r}")
        try:
            parsed = uuid.UUID(conversation_id)
        except ValueError:
            raise KeyError(conversation_id) from None
        with self._session_factory() as session:
            conversation = session.get(Conversation, parsed)
            if conversation is None:
                raise KeyError(conversation_id)
            row = Message(conversation_id=parsed, role=role, content=content)
            session.add(row)
            conversation.updated_at = datetime.now(timezone.utc)
            session.commit()
            _logger.info(
                "append role=%s conversation=%s chars=%d", role, conversation_id, len(content)
            )
            return _to_message(row)

    def rename(self, conversation_id: str, title: str) -> ConversationRecord:
        """Set title. KeyError if missing/malformed id. ValueError if title empty after normalize."""
        normalized = normalize_conversation_title(title)
        if not normalized:
            raise ValueError("title is required")
        try:
            parsed = uuid.UUID(conversation_id)
        except ValueError:
            raise KeyError(conversation_id) from None
        with self._session_factory() as session:
            row = session.get(Conversation, parsed)
            if row is None:
                raise KeyError(conversation_id)
            row.title = normalized
            session.commit()
            _logger.info("rename conversation=%s", conversation_id)
            return _to_conversation(row)

    def delete(self, conversation_id: str) -> None:
        """Delete conversation and its messages (CASCADE). KeyError if missing/malformed id."""
        try:
            parsed = uuid.UUID(conversation_id)
        except ValueError:
            raise KeyError(conversation_id) from None
        with self._session_factory() as session:
            row = session.get(Conversation, parsed)
            if row is None:
                raise KeyError(conversation_id)
            session.delete(row)
            session.commit()
            _logger.info("delete conversation=%s", conversation_id)


def _to_conversation(row: Conversation) -> ConversationRecord:
    """Map an ORM Conversation to its plain DTO."""
    return ConversationRecord(
        id=str(row.id),
        title=row.title,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_message(row: Message) -> MessageRecord:
    """Map an ORM Message to its plain DTO."""
    return MessageRecord(
        id=str(row.id),
        conversation_id=str(row.conversation_id),
        role=row.role,
        content=row.content,
        created_at=row.created_at,
    )
