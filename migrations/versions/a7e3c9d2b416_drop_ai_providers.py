"""Drop ai_providers: SQLDesk calls no model itself

0.6.0-rc.1 shipped a table for the model an organization talks to, for
features that never used it -- MCP serves tools to the client's model and
calls none of its own. The table goes before 0.6.0 so that nobody's first
install carries a credential store for a feature that does not exist.

`IF EXISTS`, because an install that went from 0.5 straight to this revision
never had the table if `create_tables` built the schema from the models.

Revision ID: a7e3c9d2b416
Revises: f6b4e2c8d195
"""

import sqlalchemy as sa
from alembic import op

revision = "a7e3c9d2b416"
down_revision = "f6b4e2c8d195"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("DROP INDEX IF EXISTS ix_ai_providers_org_id")
    op.execute("DROP TABLE IF EXISTS ai_providers")


def downgrade():
    op.create_table(
        "ai_providers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("org_id", sa.Integer(), nullable=True),
        sa.Column("type", sa.String(length=255), nullable=True),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column("base_url", sa.String(length=1024), nullable=True),
        sa.Column("encrypted_options", sa.LargeBinary(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_providers_org_id", "ai_providers", ["org_id"], unique=True)
