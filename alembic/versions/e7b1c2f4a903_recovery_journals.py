"""Create the recovery journals: workspace state, mutations, previews, jobs, repairs.

Revision ID: e7b1c2f4a903
Revises: d4a7e1b90c22
"""
import sqlalchemy as sa
from alembic import op

revision = "e7b1c2f4a903"
down_revision = "d4a7e1b90c22"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "workspace_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("seq", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_commit", sa.Text(), nullable=True),
        sa.Column("maintenance_job_id", sa.Text(), nullable=True),
        sa.Column("maintenance_kind", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_table(
        "mutation_records",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("operation_id", sa.Text(), nullable=False, unique=True),
        sa.Column("origin_kind", sa.Text(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("branch_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("run_id", sa.Text(), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("paths", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("before_hashes", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("before_commit", sa.Text(), nullable=True),
        sa.Column("after_commit", sa.Text(), nullable=True),
        sa.Column("workspace_seq", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.Text(), nullable=False, server_default="applied"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_mutation_records_conversation", "mutation_records", ["conversation_id"])
    op.create_index("ix_mutation_records_after_commit", "mutation_records", ["after_commit"])
    op.create_table(
        "recovery_previews",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("conversation_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("message_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("expected_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("plan", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "recovery_jobs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("operation_id", sa.Text(), nullable=False, unique=True),
        sa.Column("conversation_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("message_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("preview_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="prepared"),
        sa.Column("stage", sa.Text(), nullable=True),
        sa.Column("plan", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("candidate_config", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("edited_content", sa.Text(), nullable=True),
        sa.Column("confirmed_paths", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("prepared_turn_id", sa.Text(), nullable=True),
        sa.Column("completed_paths", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_recovery_jobs_conversation", "recovery_jobs", ["conversation_id"])
    op.create_table(
        "index_repairs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("body_hash", sa.Text(), nullable=True),
        sa.Column("fingerprint", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("operation_id", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_index_repairs_status", "index_repairs", ["status"])


def downgrade():
    op.drop_index("ix_index_repairs_status", table_name="index_repairs")
    op.drop_table("index_repairs")
    op.drop_index("ix_recovery_jobs_conversation", table_name="recovery_jobs")
    op.drop_table("recovery_jobs")
    op.drop_table("recovery_previews")
    op.drop_index("ix_mutation_records_after_commit", table_name="mutation_records")
    op.drop_index("ix_mutation_records_conversation", table_name="mutation_records")
    op.drop_table("mutation_records")
    op.drop_table("workspace_state")
