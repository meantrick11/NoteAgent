"""conversation branches, runs, boundaries and backend metadata

Revision ID: b1e7c4a90d23
Revises: a9b4c2d1e8f0
Create Date: 2026-10-01

LangGraph's own checkpoint tables are created by ``saver.setup()``, not here.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b1e7c4a90d23"
down_revision: Union[str, Sequence[str], None] = "a9b4c2d1e8f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 旧库默认仍是 legacy，迁移脚本核对通过后才把单个会话切到 checkpoint。
    op.add_column(
        "conversations",
        sa.Column("active_branch_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.add_column(
        "conversations",
        sa.Column("generation", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "conversations",
        sa.Column("state_backend", sa.Text(), nullable=False, server_default="legacy"),
    )
    op.add_column(
        "conversations", sa.Column("migration_batch_id", sa.Text(), nullable=True)
    )

    op.create_table(
        "conversation_branches",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_branch_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("conversation_branches.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("fork_checkpoint_id", sa.Text(), nullable=True),
        sa.Column("head_checkpoint_id", sa.Text(), nullable=True),
        sa.Column("checkpoint_ns", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_conversation_branches_conversation",
        "conversation_branches",
        ["conversation_id"],
    )

    op.create_table(
        "conversation_runs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "branch_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("conversation_branches.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("turn_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("user_message_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("generation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("checkpoint_id", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="prepared"),
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("request_id", name="uq_conversation_runs_request"),
    )
    op.create_index(
        "ix_conversation_runs_conversation", "conversation_runs", ["conversation_id"]
    )

    op.create_table(
        "user_message_boundaries",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "branch_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("conversation_branches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("message_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("turn_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("before_checkpoint_ns", sa.Text(), nullable=False, server_default=""),
        sa.Column("before_checkpoint_id", sa.Text(), nullable=False),
        sa.Column("workspace_seq", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recoverable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "conversation_id",
            "branch_id",
            "message_id",
            name="uq_user_message_boundaries_message",
        ),
    )


def downgrade() -> None:
    op.drop_table("user_message_boundaries")
    op.drop_index("ix_conversation_runs_conversation", table_name="conversation_runs")
    op.drop_table("conversation_runs")
    op.drop_index(
        "ix_conversation_branches_conversation", table_name="conversation_branches"
    )
    op.drop_table("conversation_branches")
    op.drop_column("conversations", "migration_batch_id")
    op.drop_column("conversations", "state_backend")
    op.drop_column("conversations", "generation")
    op.drop_column("conversations", "active_branch_id")
