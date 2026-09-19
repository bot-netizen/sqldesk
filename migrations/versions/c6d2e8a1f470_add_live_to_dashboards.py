"""Add dashboards.live, for dashboards the server keeps fresh while watched

A live dashboard's queries are run by the server on an interval, once for
everyone watching, instead of by a timer in every open tab. The column holds
{"interval": seconds, "paused": bool, ...} and is null for an ordinary
dashboard, which is every existing one.

Not the vestigial `schedule` column: that one can still hold 0.2.0-era cron
schedules, and reading them as live settings would switch dashboards live
that nobody asked for.

Revision ID: c6d2e8a1f470
Revises: a8e1d0c4b726
Create Date: 2026-09-18

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "c6d2e8a1f470"
down_revision = "a8e1d0c4b726"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("dashboards", sa.Column("live", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade():
    op.drop_column("dashboards", "live")
