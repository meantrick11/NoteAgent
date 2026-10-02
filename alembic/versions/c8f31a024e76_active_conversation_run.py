"""Exclude concurrent active runs at the database boundary.

Revision ID: c8f31a024e76
Revises: b1e7c4a90d23
"""
import sqlalchemy as sa
from alembic import op

revision = "c8f31a024e76"
down_revision = "b1e7c4a90d23"
branch_labels = None
depends_on = None


def upgrade():
    # Earlier prototype prepared rows may already have published users; their
    # execution/head coordinates cannot safely be inferred from app tables.
    # Refuse those rows before any DDL instead of deleting or inventing history.
    active = op.get_bind().execute(sa.text(
        "SELECT count(*) FROM conversation_runs "
        "WHERE status IN ('prepared', 'running', 'interrupted')"
    )).scalar_one()
    if active:
        raise RuntimeError(
            "Resolve legacy active runs before upgrading: back up state, stop old "
            "workers, and reconcile their checkpoints with the previous version. "
            "No run or message has been deleted."
        )
    op.add_column("conversation_runs", sa.Column("accepted_checkpoint_id", sa.Text(), nullable=True))
    op.add_column("conversation_runs", sa.Column("lease_token", sa.Text(), nullable=True))
    op.add_column("conversation_runs", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    # Existing duplicate claims must be resolved explicitly, never silently discarded.
    op.create_index(
        "uq_conversation_runs_active", "conversation_runs", ["conversation_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('prepared', 'running', 'interrupted')"),
        sqlite_where=sa.text("status IN ('prepared', 'running', 'interrupted')"),
    )


def downgrade():
    op.drop_index("uq_conversation_runs_active", table_name="conversation_runs")
    op.drop_column("conversation_runs", "lease_expires_at")
    op.drop_column("conversation_runs", "lease_token")
    op.drop_column("conversation_runs", "accepted_checkpoint_id")
