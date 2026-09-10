"""conversations pending_draft json

Revision ID: a9b4c2d1e8f0
Revises: 8c2e1a4b7d90
Create Date: 2026-09-09

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a9b4c2d1e8f0"
down_revision: Union[str, Sequence[str], None] = "8c2e1a4b7d90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Store one pending note draft per conversation."""
    op.add_column("conversations", sa.Column("pending_draft", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Drop the pending_draft column."""
    op.drop_column("conversations", "pending_draft")
