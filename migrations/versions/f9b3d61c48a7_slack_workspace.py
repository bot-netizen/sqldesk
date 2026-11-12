"""The Slack app's bot token.

Encrypted with the same key as a data source's credentials, because it is
exactly that kind of secret: it posts as the app in every channel the app is
in, and it does not expire. One row per organisation.

Revision ID: f9b3d61c48a7
Revises: e4a7b9c20d58
"""

import sqlalchemy as sa
from alembic import op

revision = "f9b3d61c48a7"
down_revision = "e4a7b9c20d58"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "slack_workspaces",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("org_id", sa.Integer(), nullable=False),
        # LargeBinary, as `EncryptedType` stores it. This was Text until
        # d7e3ae10b9a9, which converts an install that ran the Text version:
        # it wrote the token fine and then failed every read with "string
        # argument without an encoding" -- the trap d2b81f4a7c65 warns about.
        sa.Column("encrypted_bot_token", sa.LargeBinary(), nullable=False),
        sa.Column("team_name", sa.String(length=255), nullable=True),
        sa.Column("app_name", sa.String(length=255), nullable=True),
        sa.Column("installed_by_id", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["installed_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    # One per organisation: a second token for the same workspace would be two
    # answers to "who are we posting as".
    op.create_index("slack_workspaces_org_id", "slack_workspaces", ["org_id"], unique=True)


def downgrade():
    op.drop_index("slack_workspaces_org_id", table_name="slack_workspaces")
    op.drop_table("slack_workspaces")
