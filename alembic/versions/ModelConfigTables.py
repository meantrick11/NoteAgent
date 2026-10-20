"""Create model configuration and capability tables.

Revision ID: b2f7c9d4e610
Revises: a61d9e2c4f37
"""

import sqlalchemy as sa
from alembic import op

revision = "b2f7c9d4e610"
down_revision = "a61d9e2c4f37"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "model_configs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("auth_mode", sa.String(16), nullable=False, server_default="api_key"),
        sa.Column("api_key", sa.Text(), nullable=False, server_default=""),
        sa.Column("timeout_s", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("context_window", sa.Integer(), nullable=False, server_default="32768"),
        sa.Column("temperature", sa.Float()),
        sa.Column("max_tokens", sa.Integer()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ux_model_configs_active",
        "model_configs",
        ["is_active"],
        unique=True,
        postgresql_where=sa.text("is_active"),
        sqlite_where=sa.text("is_active"),
    )
    op.create_table(
        "model_capabilities",
        sa.Column(
            "model_id",
            sa.String(64),
            sa.ForeignKey("model_configs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("capability", sa.String(32), primary_key=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("verification", sa.String(16), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True)),
        sa.Column("probe_version", sa.Integer()),
        sa.Column("evidence", sa.JSON()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade():
    op.drop_table("model_capabilities")
    op.drop_index("ux_model_configs_active", table_name="model_configs")
    op.drop_table("model_configs")
