"""Somewhere to keep which model an organization talks to

One row per org, or none. None is the default and is what makes the AI
features off until somebody configures them.

`encrypted_options` carries the API key, under the same secret and the same
column type as a data source's credentials -- the same kind of secret, and a
second mechanism would be a second thing to get wrong.

Revision ID: d2b81f4a7c65
Revises: c9f1a67b3d84
Create Date: 2026-09-24 23:40:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = "d2b81f4a7c65"
down_revision = "c9f1a67b3d84"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ai_providers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("org_id", sa.Integer(), nullable=True),
        sa.Column("type", sa.String(length=255), nullable=True),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column("base_url", sa.String(length=1024), nullable=True),
        # LargeBinary, not Text. `EncryptedType` stores ciphertext as bytes,
        # and the existing encrypted columns -- data_sources and
        # notification_destinations -- are both bytea. A Text column here
        # writes fine and then fails on every read with "string argument
        # without an encoding", which no test in this suite would have caught:
        # the schema under test comes from `create_all`, so a migration that
        # disagrees with its model is only wrong on a real database.
        sa.Column("encrypted_options", sa.LargeBinary(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    # One per organization, enforced here rather than by whoever remembers to
    # look first.
    op.create_index("ix_ai_providers_org_id", "ai_providers", ["org_id"], unique=True)


def downgrade():
    op.drop_index("ix_ai_providers_org_id", table_name="ai_providers")
    op.drop_table("ai_providers")
