"""Index the live dashboards, which are swept every ten seconds

`refresh_live_dashboards` runs on the periodic scheduler every ten seconds and
asks for exactly one set of rows: dashboards with `live IS NOT NULL` that are
not archived. With no index that is a sequential scan of every dashboard in
the installation, six times a minute, for ever -- and it is a scan whose
answer is almost always a handful of rows or none at all.

Partial, because "live" is the rare case. The index holds only the live
dashboards rather than a row per dashboard, so it stays small whatever the
table does, and Postgres can use it for this predicate alone.

Revision ID: a3f5c07be41d
Revises: c4a71d9e2f18
Create Date: 2026-09-23

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "a3f5c07be41d"
down_revision = "c4a71d9e2f18"
branch_labels = None
depends_on = None

INDEX_NAME = "ix_dashboards_live"


def upgrade():
    op.create_index(
        INDEX_NAME,
        "dashboards",
        ["id"],
        postgresql_where=op.inline_literal("live IS NOT NULL AND is_archived = false"),
    )


def downgrade():
    op.drop_index(INDEX_NAME, table_name="dashboards")
