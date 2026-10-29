"""A subscription that fails backs off instead of trying every minute

When it was last tried and how many tries in a row have failed, so a send
that keeps failing waits 2, 4, 8 ... up to 60 minutes between tries rather
than redrawing and remailing every minute.

Revision ID: e5c1a9b3d7f2
Revises: d4b2a8e61f37
Create Date: 2026-10-23

"""

import sqlalchemy as sa
from alembic import op

revision = "e5c1a9b3d7f2"
down_revision = "d4b2a8e61f37"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("dashboard_subscriptions", sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "dashboard_subscriptions", sa.Column("failures", sa.Integer(), nullable=False, server_default="0")
    )


def downgrade():
    op.drop_column("dashboard_subscriptions", "failures")
    op.drop_column("dashboard_subscriptions", "last_attempt_at")
