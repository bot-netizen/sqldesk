"""A notebook can run itself on a cron.

Only cron, deliberately: a notebook is run by somebody who wants it done at a
time — "every morning before the standup" — where the query scheduler's
interval/time/day_of_week trio answers a different question, which is "keep
this no more than an hour stale".

`last_scheduled_at` is separate from any cell's `last_run_at` so that running
one cell by hand does not look to the scheduler like the whole notebook has
just run.

Revision ID: 6d2a8e34f71b
Revises: 5c1f7a92b4d8
Create Date: 2026-10-31

"""

import sqlalchemy as sa
from alembic import op

revision = "6d2a8e34f71b"
down_revision = "5c1f7a92b4d8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("notebooks", sa.Column("schedule", sa.String(length=255), nullable=True))
    op.add_column("notebooks", sa.Column("schedule_failures", sa.Integer(), nullable=True, server_default="0"))
    op.add_column("notebooks", sa.Column("last_scheduled_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("notebooks", "last_scheduled_at")
    op.drop_column("notebooks", "schedule_failures")
    op.drop_column("notebooks", "schedule")
