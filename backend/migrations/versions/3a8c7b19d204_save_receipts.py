"""Add save idempotency receipts without modifying existing records.

Revision ID: 3a8c7b19d204
Revises: d15dba763f15
"""
from alembic import op
import sqlalchemy as sa

revision = "3a8c7b19d204"
down_revision = "d15dba763f15"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "save_requests",
        sa.Column("key_hash", sa.String(64), primary_key=True),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("version_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["version_id"], ["rate_versions.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_save_requests_version_id", "save_requests", ["version_id"])
    op.create_index("ix_save_requests_created_at", "save_requests", ["created_at"])


def downgrade():
    # Explicit operator action only; application rollback can leave this table.
    op.drop_table("save_requests")
