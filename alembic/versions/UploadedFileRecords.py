"""Keep independent uploaded-file records and their physical paths.

Revision ID: a61d9e2c4f37
Revises: f8c2d3e5b014
"""
import uuid

import sqlalchemy as sa
from alembic import op


revision = "a61d9e2c4f37"
down_revision = "f8c2d3e5b014"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_index("uq_active_source_sha256", table_name="source_files")
    op.add_column("source_files", sa.Column("original_filename", sa.Text(), nullable=True))
    op.add_column("source_files", sa.Column("storage_path", sa.Text(), nullable=True))
    table = sa.table("source_files", sa.column("id", sa.Uuid(as_uuid=True)),
                     sa.column("display_name", sa.Text()), sa.column("original_filename", sa.Text()),
                     sa.column("storage_path", sa.Text()))
    connection = op.get_bind()
    for source_id, display_name in connection.execute(sa.select(table.c.id, table.c.display_name)):
        path = str(source_id if isinstance(source_id, uuid.UUID) else uuid.UUID(str(source_id)))
        connection.execute(sa.update(table).where(table.c.id == source_id).values(
            original_filename=display_name, storage_path=path))
    with op.batch_alter_table("source_files") as batch:
        batch.alter_column("original_filename", existing_type=sa.Text(), nullable=False)
        batch.alter_column("storage_path", existing_type=sa.Text(), nullable=False)


def downgrade():
    duplicates = op.get_bind().execute(sa.text("""
        SELECT sha256 FROM source_files WHERE status != 'deleted'
        GROUP BY sha256 HAVING COUNT(*) > 1 LIMIT 1
    """)).first()
    if duplicates is not None:
        raise RuntimeError("存在同 SHA-256 的独立上传记录，不能恢复旧版唯一约束")
    with op.batch_alter_table("source_files") as batch:
        batch.drop_column("storage_path")
        batch.drop_column("original_filename")
    op.create_index("uq_active_source_sha256", "source_files", ["sha256"], unique=True,
                    postgresql_where=sa.text("status != 'deleted'"),
                    sqlite_where=sa.text("status != 'deleted'"))
