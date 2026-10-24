"""A paused data source stays paused across a Redis restart

Pausing a data source is what an administrator does when the warehouse is
overloaded or being migrated, and it lived only in Redis -- so it lasted until
the next Redis restart, after which every scheduled query ran against that
warehouse again and nothing said anything. The decision belongs in Postgres.

Existing pauses are not migrated: the Redis key is still read as a fallback,
and still written, so a worker on the previous version sees a pause made by
this one during a rolling upgrade.

Revision ID: d18e3b57ca04
Revises: c92f4a6b8d31
Create Date: 2026-10-24

"""

import sqlalchemy as sa
from alembic import op

revision = "d18e3b57ca04"
down_revision = "c92f4a6b8d31"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("data_sources", sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("data_sources", sa.Column("paused_note", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("data_sources", "paused_note")
    op.drop_column("data_sources", "paused_at")
