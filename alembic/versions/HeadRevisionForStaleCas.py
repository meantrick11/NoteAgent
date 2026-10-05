"""Add a monotonic head revision for stale-tab CAS.

Revision ID: d4a7e1b90c22
Revises: c8f31a024e76
"""
import sqlalchemy as sa
from alembic import op

revision = "d4a7e1b90c22"
down_revision = "c8f31a024e76"
branch_labels = None
depends_on = None


def upgrade():
    # Existing rows start at 0; the next publish increments to 1. Backfilling a
    # fabricated history is neither possible nor useful: only future edits need it.
    op.add_column(
        "conversations",
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade():
    op.drop_column("conversations", "revision")
