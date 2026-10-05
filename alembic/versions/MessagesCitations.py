"""messages citations json

Revision ID: 8c2e1a4b7d90
Revises: 3d1c2b8a9e4f
Create Date: 2026-09-07

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "8c2e1a4b7d90"
down_revision: Union[str, Sequence[str], None] = "3d1c2b8a9e4f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Store used citation mappings on assistant messages."""
    op.add_column("messages", sa.Column("citations", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Drop the citations column."""
    op.drop_column("messages", "citations")
