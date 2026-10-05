"""context watermark and tool stubs

Revision ID: 3d1c2b8a9e4f
Revises: f16dee6e3c97
Create Date: 2026-08-26

"""
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '3d1c2b8a9e4f'
down_revision: Union[str, Sequence[str], None] = 'f16dee6e3c97'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _backfill_turn_ids() -> None:
    """Assign a turn_id to legacy rows: each user opens a turn, following rows share it."""
    bind = op.get_bind()
    messages = sa.table(
        "messages",
        sa.column("id", sa.Uuid(as_uuid=True)),
        sa.column("conversation_id", sa.Uuid(as_uuid=True)),
        sa.column("role", sa.Text()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("turn_id", sa.Uuid(as_uuid=True)),
    )
    rows = bind.execute(
        sa.select(
            messages.c.id,
            messages.c.conversation_id,
            messages.c.role,
        ).order_by(
            messages.c.conversation_id,
            messages.c.created_at,
            messages.c.id,
        )
    ).fetchall()
    current: dict = {}
    for row in rows:
        conversation_id = row.conversation_id
        if row.role == "user":
            turn = uuid.uuid4()
            current[conversation_id] = turn
        else:
            turn = current.get(conversation_id)
        if turn is not None:
            bind.execute(
                messages.update()
                .where(messages.c.id == row.id)
                .values(turn_id=turn)
            )


def upgrade() -> None:
    """Add summary/watermark columns and tool-stub columns, then backfill turn ids."""
    op.add_column("conversations", sa.Column("running_summary", sa.Text(), nullable=True))
    op.add_column(
        "conversations",
        sa.Column("summary_watermark_turn_id", sa.Uuid(), nullable=True),
    )
    op.add_column("messages", sa.Column("turn_id", sa.Uuid(), nullable=True))
    op.add_column("messages", sa.Column("tool_name", sa.Text(), nullable=True))
    op.add_column("messages", sa.Column("tool_arguments", sa.Text(), nullable=True))
    op.add_column("messages", sa.Column("output_preview", sa.Text(), nullable=True))
    op.add_column(
        "messages",
        sa.Column("truncated", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("messages", sa.Column("status", sa.Text(), nullable=True))
    op.create_index(
        "ix_messages_conversation_turn",
        "messages",
        ["conversation_id", "turn_id"],
        unique=False,
    )
    _backfill_turn_ids()


def downgrade() -> None:
    """Drop the context columns and the turn index."""
    op.drop_index("ix_messages_conversation_turn", table_name="messages")
    op.drop_column("messages", "status")
    op.drop_column("messages", "truncated")
    op.drop_column("messages", "output_preview")
    op.drop_column("messages", "tool_arguments")
    op.drop_column("messages", "tool_name")
    op.drop_column("messages", "turn_id")
    op.drop_column("conversations", "summary_watermark_turn_id")
    op.drop_column("conversations", "running_summary")
