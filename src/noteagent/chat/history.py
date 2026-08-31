"""Persistence for chat history: conversations and their messages.

This is the only write path for user-visible history. HTTP handlers call
``ConversationStore``; they never ``session.add`` directly.
"""

import logging
import uuid
from dataclasses import dataclass   #进行类的初始化，不过不像BaseModel进行参数校验
from datetime import datetime, timezone #时间记录，对应的消息记录创建的时间等等


from sqlalchemy import select   #ORM的select语句的方法
from sqlalchemy.orm import Session, sessionmaker    #高级封装，直接操作数据库

from noteagent.chat.context_tokens import prefix_until_tokens
from noteagent.db.models import Conversation, Message   #

_logger = logging.getLogger(__name__)

_ROLES = {"user", "assistant"}

#获取第一次的对话的User的消息作为新对话的标题title
def conversation_title_from_question(question: str, max_len: int = 40) -> str:
    """Collapse whitespace and truncate for the sidebar title."""
    
    text = " ".join(question.split())
    if not text:
        return "新对话"
    return text if len(text) <= max_len else text[:max_len]


##对传入的对话的命名titile进行标准化，去掉左右空格+限制最大长度->title(str)
def normalize_conversation_title(title: str, max_len: int = 80) -> str:
    """Collapse whitespace; return "" if nothing left; raise if over max_len."""
    text = " ".join(title.split())
    if len(text) > max_len:
        raise ValueError("title too long")
    return text


def start_turn() -> str:
    """Return str(uuid.uuid4()). No DB write."""
    return str(uuid.uuid4())


def _uuid(turn_id: str) -> uuid.UUID:
    """Parse a turn_id string into a UUID; raises ValueError if malformed."""
    return uuid.UUID(turn_id)


@dataclass(slots=True)
class ConversationRecord:   #对话的记录，记录id\title（对话名称),创建和更新时间
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    running_summary: str | None
    summary_watermark_turn_id: str | None


@dataclass(slots=True)  #对于每一条消息，进行数据库记录：
class MessageRecord:
    id: str
    conversation_id: str
    role: str
    content: str
    created_at: datetime
    turn_id: str | None
    tool_name: str | None
    tool_arguments: str | None
    output_preview: str | None
    truncated: bool
    status: str | None


class ConversationStore:
    """Persist conversations and messages. One short-lived Session per method."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def create(self, title: str) -> ConversationRecord:
        """Insert a new conversation and return its record."""
        #涉及新的对话的创建，才进行ConversationRecord的记录
        with self._session_factory() as session:
            row = Conversation(title=title)
            session.add(row)
            session.commit()
            _logger.info("created conversation=%s", row.id)
            return _to_conversation(row)
    # 通过conversation_id从数据库中获取对应的会话记录，然后返回Conversation_id给前端解析
    def get(self, conversation_id: str) -> ConversationRecord | None:
        """Return a conversation by id, or None if missing or malformed."""
        try:
            parsed = uuid.UUID(conversation_id)
        except ValueError:
            return None
        with self._session_factory() as session:
            row = session.get(Conversation, parsed)
            return _to_conversation(row) if row is not None else None
    
    #获取数据库中所有存在的conversation的历史
    def list_conversations(self) -> list[ConversationRecord]:
        """Return all conversations ordered by updated_at DESC, created_at DESC."""
        
        with self._session_factory() as session:
            rows = session.scalars(
                select(Conversation).order_by(
                    Conversation.updated_at.desc(), 
                    Conversation.created_at.desc(),
                )
            ).all() #按照最近更新时间排序，其次是创建时间
            return [_to_conversation(row) for row in rows]
    # 传入conversation_id，然后传出对应的conversation的一系列的历史消息
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
                .where(Message.role.in_(("user", "assistant")))
                .order_by(Message.created_at.asc(), Message.id.asc())
            ).all()
            return [_to_message(row) for row in rows]
     #如果遇到新的消息需要添加到conversation_id的对话中去，执行此函数获取对应的Message存储格式
    def append_message(
        self, conversation_id: str, role: str, content: str, *, turn_id: str
    ) -> MessageRecord:
        """Insert a user/assistant message and bump the conversation's updated_at.

        Raises KeyError if the conversation is missing or the id is malformed;
        ValueError if role is not in {user, assistant} or turn_id is empty.
        """

        if role not in _ROLES:  #只有{user,assistant}两种角色
            raise ValueError(f"invalid role: {role!r}")
        if not turn_id:
            raise ValueError("turn_id is required")
        try:
            parsed = uuid.UUID(conversation_id)
        except ValueError:
            raise KeyError(conversation_id) from None
        turn = _uuid(turn_id)
        with self._session_factory() as session:
            conversation = session.get(Conversation, parsed)
            if conversation is None:
                raise KeyError(conversation_id)
            row = Message(conversation_id=parsed, role=role, content=content, turn_id=turn)
            session.add(row)
            conversation.updated_at = datetime.now(timezone.utc)
            session.commit()
            _logger.info(
                "append role=%s conversation=%s turn=%s chars=%d",
                role, conversation_id, turn_id, len(content),
            )
            return _to_message(row)
        
    def append_tool_stub(
        self,
        conversation_id: str,
        *,
        turn_id: str,
        tool_name: str,
        arguments: str,
        output: str,
        status: str,
        stub_preview_tokens: int,
        args_preview_chars: int,
    ) -> MessageRecord:
        """Insert a role='tool' stub without bumping conversation.updated_at.

        Truncate arguments by character count args_preview_chars; truncate
        output to stub_preview_tokens via prefix_until_tokens. The stored
        content equals output_preview (NOT NULL). status must be ok or error.
        """
        if status not in ("ok", "error"):
            raise ValueError(f"invalid status: {status!r}")
        try:
            parsed = uuid.UUID(conversation_id)
        except ValueError:
            raise KeyError(conversation_id) from None
        turn = _uuid(turn_id)
        args_preview = arguments[:args_preview_chars] if args_preview_chars > 0 else ""
        out_preview, truncated = prefix_until_tokens(output, stub_preview_tokens)
        with self._session_factory() as session:
            conversation = session.get(Conversation, parsed)
            if conversation is None:
                raise KeyError(conversation_id)
            row = Message(
                conversation_id=parsed,
                role="tool",
                content=out_preview,
                turn_id=turn,
                tool_name=tool_name,
                tool_arguments=args_preview,
                output_preview=out_preview,
                truncated=truncated,
                status=status,
            )
            session.add(row)
            session.commit()
            _logger.info(
                "tool stub conversation=%s turn=%s tool=%s status=%s preview_tokens=%d",
                conversation_id, turn_id, tool_name, status, stub_preview_tokens,
            )
            return _to_message(row)

    def list_persistent_after_watermark(self, conversation_id: str) -> list[MessageRecord]:
        """Return all roles strictly after the watermark turn, or all if NULL.

        Raises KeyError if the conversation is missing or the id is malformed.
        """
        try:
            parsed = uuid.UUID(conversation_id)
        except ValueError:
            raise KeyError(conversation_id) from None
        with self._session_factory() as session:
            conversation = session.get(Conversation, parsed)
            if conversation is None:
                raise KeyError(conversation_id)
            rows = session.scalars(
                select(Message)
                .where(Message.conversation_id == parsed)
                .order_by(Message.created_at.asc(), Message.id.asc())
            ).all()
            watermark = conversation.summary_watermark_turn_id
            if watermark is None:
                records = [_to_message(r) for r in rows]
            else:
                records = [_to_message(r) for r in _turns_after_watermark(rows, watermark)]
            _logger.info(
                "load persistent conversation=%s rows=%d watermark=%s",
                conversation_id,
                len(records),
                str(watermark) if watermark is not None else "none",
            )
            return records

    def apply_compact(
        self,
        conversation_id: str,
        *,
        summary_append: str,
        watermark_turn_id: str,
    ) -> None:
        """Append summary_append to running_summary and advance the watermark.

        Appends with a blank-line separator; never rewrites the old summary.
        Raises KeyError if the conversation is missing or the id is malformed.
        """
        try:
            parsed = uuid.UUID(conversation_id)
        except ValueError:
            raise KeyError(conversation_id) from None
        watermark = _uuid(watermark_turn_id)
        with self._session_factory() as session:
            conversation = session.get(Conversation, parsed)
            if conversation is None:
                raise KeyError(conversation_id)
            old = conversation.running_summary
            if old and old.strip():
                new = old.rstrip() + "\n\n" + summary_append.strip()
            else:
                new = summary_append.strip()
            conversation.running_summary = new
            conversation.summary_watermark_turn_id = watermark
            session.commit()
            _logger.info(
                "compact conversation=%s watermark=%s summary_chars=%d",
                conversation_id, watermark_turn_id, len(new),
            )

    #rename逻辑，需要传入对应的Id的名字+新的title的命名，输出历史消息记录的类，需要对数据库进行操作
    def rename(self, conversation_id: str, title: str) -> ConversationRecord:
        """Set title. KeyError if missing/malformed id. ValueError if title empty after normalize."""
        normalized = normalize_conversation_title(title)        #先将title进行标准化
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
        
    #delete逻辑，需要对数据库对应的UUID的conversation_id的对话进行删除
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

def _turns_after_watermark(rows: list[Message], watermark) -> list[Message]:
    """Return rows whose turn comes strictly after the watermark turn.

    Groups rows by turn_id (group order = first row's created_at order). Rows
    with turn_id None form singleton groups. If the watermark group is missing,
    return all rows (treated as never summarized).
    """
    groups: dict = {}
    order: list = []
    for row in rows:
        key = row.turn_id if row.turn_id is not None else row.id
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(row)
    if watermark not in groups:
        return rows
    idx = order.index(watermark)
    result: list[Message] = []
    for key in order[idx + 1:]:
        result.extend(groups[key])
    return result

#将数据库中查询的SQLAIchemy的Model转换为对应的python可用的ConversationRecord类
def _to_conversation(row: Conversation) -> ConversationRecord:
    """Map an ORM Conversation to its plain DTO."""
    return ConversationRecord(
        id=str(row.id),
        title=row.title,
        created_at=row.created_at,
        updated_at=row.updated_at,
        running_summary=row.running_summary,
        summary_watermark_turn_id=(
            str(row.summary_watermark_turn_id)
            if row.summary_watermark_turn_id is not None
            else None
        ),
    )

#将从数据库中查询出来的Message转换为Python可用的MessageRecord类
def _to_message(row: Message) -> MessageRecord:
    """Map an ORM Message to its plain DTO."""
    #遇到新的消息对话，进行Message转换
    return MessageRecord(
        id=str(row.id),
        conversation_id=str(row.conversation_id),
        role=row.role,
        content=row.content,
        created_at=row.created_at,
        turn_id=str(row.turn_id) if row.turn_id is not None else None,
        tool_name=row.tool_name,
        tool_arguments=row.tool_arguments,
        output_preview=row.output_preview,
        truncated=bool(row.truncated),
        status=row.status,
    )
