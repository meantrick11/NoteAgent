"""ORM tables that track branches, runs, and recovery boundaries.

These sit beside the LangGraph checkpoint tables the saver owns; this module never
re-implements them. ``Base`` always comes from :mod:`NoteAgent.BusinessModules.ConversationState.models`.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from NoteAgent.TechnicalSupport.DatabaseAccess.OrmBase import Base


from sqlalchemy import JSON
from sqlalchemy.orm import relationship

def _utcnow() -> datetime:
    """Return UTC timestamps for conversation and run records."""
    return datetime.now(timezone.utc)


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
    pending_draft: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # 待审 NoteDraft JSON，无稿为 NULL
    # 活动分支与写入隔离代数：由 conversations 服务维护，不由 saver 的“最新 checkpoint”推断。
    active_branch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 每次发布活动 head（聊天完成、草稿编辑／清除）自增；供前端 stale 校验使用。
    # 与 generation 分开：generation 只在换分支时变，revision 每次都变。
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # legacy：消息权威源仍在旧表；checkpoint：权威源已切到 LangGraph checkpoint。
    state_backend: Mapped[str] = mapped_column(Text, nullable=False, default="legacy")
    migration_batch_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )   #具体的message表的映射


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
    citations: Mapped[list | None] = mapped_column(JSON, nullable=True)  # assistant 实际引用的来源映射
    conversation: Mapped[Conversation] = relationship(back_populates="messages")    #关联的conversation表id


class ConversationBranch(Base):
    """One logical conversation branch; its head pins the active checkpoint."""

    __tablename__ = "conversation_branches"
    __table_args__ = (
        Index("ix_conversation_branches_conversation", "conversation_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    parent_branch_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversation_branches.id", ondelete="SET NULL"), nullable=True
    )
    # Checkpoint this branch forked from; NULL for a root branch.
    fork_checkpoint_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    head_checkpoint_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    checkpoint_ns: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )


class ConversationRun(Base):
    """One prepared turn's execution claim, so a turn runs at most once."""

    __tablename__ = "conversation_runs"
    __table_args__ = (
        UniqueConstraint("request_id", name="uq_conversation_runs_request"),
        Index("ix_conversation_runs_conversation", "conversation_id"),
        Index(
            "uq_conversation_runs_active", "conversation_id", unique=True,
            postgresql_where=text("status IN ('prepared', 'running', 'interrupted')"),
            sqlite_where=text("status IN ('prepared', 'running', 'interrupted')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversation_branches.id", ondelete="SET NULL"), nullable=True
    )
    turn_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    user_message_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    checkpoint_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    accepted_checkpoint_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    lease_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="prepared")
    request_id: Mapped[str] = mapped_column(Text, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )


class UserMessageBoundary(Base):
    """The safe checkpoint captured just before one user message was accepted."""

    __tablename__ = "user_message_boundaries"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            "branch_id",
            "message_id",
            name="uq_user_message_boundaries_message",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversation_branches.id", ondelete="CASCADE"), nullable=False
    )
    message_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    turn_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    # Explicit before-config: never resolve a boundary through the saver's "latest".
    before_checkpoint_ns: Mapped[str] = mapped_column(
        Text, nullable=False, default=""
    )
    before_checkpoint_id: Mapped[str] = mapped_column(Text, nullable=False)
    workspace_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recoverable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
