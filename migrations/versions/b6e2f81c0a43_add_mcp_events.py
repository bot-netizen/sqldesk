"""An audit of what MCP clients ask for

Written for every request including the refused ones: an audit that records
only what succeeded answers "what did this work do" and not "who has been
trying", and the second is the question somebody asks at two in the morning.

Revision ID: b6e2f81c0a43
Revises: f3a90c15d7e8
Create Date: 2026-09-25 02:10:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = "b6e2f81c0a43"
down_revision = "f3a90c15d7e8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mcp_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("org_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column("client", sa.String(length=255), nullable=True),
        sa.Column("method", sa.String(length=64), nullable=True),
        sa.Column("tool", sa.String(length=64), nullable=True),
        sa.Column("outcome", sa.String(length=16), nullable=True),
        sa.Column("detail", sa.String(length=1024), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("remote_addr", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    # Every read is "the most recent, for this org", and this is the
    # fastest-growing table 0.6 adds.
    op.create_index("ix_mcp_events_org_created_at", "mcp_events", ["org_id", "created_at"])


def downgrade():
    op.drop_index("ix_mcp_events_org_created_at", table_name="mcp_events")
    op.drop_table("mcp_events")
