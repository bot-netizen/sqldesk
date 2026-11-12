"""A dashboard subscription can post to a Slack channel

The channel's id, which is what Slack posts by, and its name as it was when
picked, which is what the subscription dialog lists. Both empty for a
subscription that mails people, which is every subscription made before this.

Revision ID: a8d3f6c1e924
Revises: 6d2a8e34f71b
Create Date: 2026-11-12

"""

import sqlalchemy as sa
from alembic import op

revision = "a8d3f6c1e924"
down_revision = "6d2a8e34f71b"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("dashboard_subscriptions", sa.Column("slack_channel", sa.String(length=64), nullable=True))
    op.add_column("dashboard_subscriptions", sa.Column("slack_channel_name", sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column("dashboard_subscriptions", "slack_channel_name")
    op.drop_column("dashboard_subscriptions", "slack_channel")
