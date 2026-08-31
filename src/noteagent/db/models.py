"""SQLAlchemy ORM models for chat history.

Only ``Base`` and the two tables live here. No HTTP, no LLM calls.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Text, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base shared by all noteagent tables."""


def _utcnow() -> datetime:
    """Return the current UTC time for timestamp column defaults."""
    return datetime.now(timezone.utc)

# 数据库层的Conversation的映射，ORM模型，和数据库直接绑定对应的column
class Conversation(Base):
    """A single chat thread shown in the sidebar."""

    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_updated_at", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    running_summary: Mapped[str | None] = mapped_column(Text, nullable=True)    #持续的摘要字段总结，旧摘要+新摘要
    summary_watermark_turn_id: Mapped[uuid.UUID | None] = mapped_column(    
        Uuid(as_uuid=True), nullable=True
    )   #最近摘要的水位线
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )   #具体的message表的映射

#同样的数据库层面的ORM模型，进行python数据Message层级的映射
class Message(Base):
    """One user or assistant bubble in a conversation."""

    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
        Index("ix_messages_conversation_turn", "conversation_id", "turn_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )   
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(Text, nullable=False) #消息的类型：user\assistant,tool Message
    content: Mapped[str] = mapped_column(Text, nullable=False)  #具体的内容，全量保存user&assistant的最终回复，部分工具调用信息，比如工具名，输入参数，截断的具体工具输出
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )   #Message创建的时间
    turn_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)    #具体的对话轮数
    tool_name: Mapped[str | None] = mapped_column(Text, nullable=True)  #
    tool_arguments: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str | None] = mapped_column(Text, nullable=True)
    conversation: Mapped[Conversation] = relationship(back_populates="messages")    #关联的conversation表id
