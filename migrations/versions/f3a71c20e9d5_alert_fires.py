"""An alert keeps a history of when it fired

The alert row carries only `state` and `last_triggered_at` -- where it is now
and when it last moved -- so an alert that has gone off four times since
breakfast looks exactly like one that went off once and stayed there. This is
one row per state change, with the value it was evaluating at the time.

Revision ID: f3a71c20e9d5
Revises: d18e3b57ca04
Create Date: 2026-10-27

"""

import sqlalchemy as sa
from alembic import op

revision = "f3a71c20e9d5"
down_revision = "d18e3b57ca04"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "alert_fires",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("alert_id", sa.Integer(), nullable=True),
        sa.Column("state", sa.String(length=255), nullable=True),
        sa.Column("value", sa.String(length=255), nullable=True),
        sa.Column("notified", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        # ondelete rather than only the ORM cascade: deleting an alert through
        # anything that is not a session -- a migration, psql -- should not
        # leave its history behind pointing at nothing.
        sa.ForeignKeyConstraint(["alert_id"], ["alerts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    # Every read is "one alert, newest first": the count on the list and the
    # history on the page.
    op.create_index("alert_fires_alert_id_created_at", "alert_fires", ["alert_id", "created_at"])


def downgrade():
    op.drop_index("alert_fires_alert_id_created_at", table_name="alert_fires")
    op.drop_table("alert_fires")
