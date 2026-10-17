"""Create independent uploaded-source storage metadata.

Revision ID: f8c2d3e5b014
Revises: e7b1c2f4a903
"""
import sqlalchemy as sa
from alembic import op

revision = "f8c2d3e5b014"
down_revision = "e7b1c2f4a903"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "source_files",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("folder", sa.Text(), nullable=False),
        sa.Column("media_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("parse_profile_id", sa.Text()),
        sa.Column("parse_profile_revision", sa.Integer()),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("uq_active_source_sha256", "source_files", ["sha256"], unique=True,
                    postgresql_where=sa.text("status != 'deleted'"),
                    sqlite_where=sa.text("status != 'deleted'"))
    op.create_table("source_folders", sa.Column("name", sa.Text(), primary_key=True))
    op.create_table(
        "source_fragments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_file_id", sa.Uuid(as_uuid=True), sa.ForeignKey("source_files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("locator", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.UniqueConstraint("source_file_id", "ordinal"),
    )


def downgrade():
    op.drop_table("source_fragments")
    op.drop_table("source_folders")
    op.drop_index("uq_active_source_sha256", table_name="source_files")
    op.drop_table("source_files")
