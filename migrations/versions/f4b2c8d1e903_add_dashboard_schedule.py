"""Add a refresh schedule to dashboards

A dashboard has no data of its own -- it is a view over the queries behind its
widgets -- so this schedule means "refresh those queries on this cadence".
Same shape as a query's schedule, so the same crontab expression and the same
code decide when a slot has come round.

Revision ID: f4b2c8d1e903
Revises: c3e9a1f5d7b2
Create Date: 2026-09-17

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = "f4b2c8d1e903"
down_revision = "c3e9a1f5d7b2"
branch_labels = None
depends_on = None


def upgrade():
    # Nullable, with no default: a dashboard without a schedule holds SQL NULL
    # rather than an empty dict, which is what "not scheduled" means for a
    # query too, so the two read the same way.
    op.add_column("dashboards", sa.Column("schedule", JSONB(astext_type=sa.Text()), nullable=True))


def downgrade():
    op.drop_column("dashboards", "schedule")
