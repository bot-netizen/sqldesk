"""Index events for the admin overview

`events` carries a row for every query anyone runs and has never had an index
beyond its primary key. The admin overview asks it who has been running
queries in the last hour, which without this is a full table scan -- measured
on a small instance at 22,444 rows: seq scan, 1,170 buffers, 26.9 ms, to
return 47 rows. That cost grows with every execution ever recorded, so the
page would get slower precisely as the instance got busier, which is when
somebody is looking at it.

`(org_id, action, created_at)` in that order because it is exactly the
predicate: one organization, one kind of event, a window of time.

Created concurrently is not possible inside Alembic's transaction, so on a
large existing `events` table this takes a lock for as long as the build
takes. It is one index on one table and the alternative is a page nobody can
use.

Revision ID: b8f3c5d21a07
Revises: c6d2e8a1f470
Create Date: 2026-09-21

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "b8f3c5d21a07"
down_revision = "c6d2e8a1f470"
branch_labels = None
depends_on = None

INDEX_NAME = "ix_events_org_action_created_at"


def upgrade():
    op.create_index(INDEX_NAME, "events", ["org_id", "action", "created_at"])


def downgrade():
    op.drop_index(INDEX_NAME, table_name="events")
