"""add row_count to query_results

Denormalised so list views can show how many rows a query returned without
loading QueryResult.data. Query.all_queries() deliberately narrows its join
to runtime/retrieved_at to keep result payloads out of list queries, and
reading `data` there would undo that on every request.

Nullable on purpose: existing rows are not backfilled. Counting them would
mean parsing every stored result — potentially gigabytes of JSON — for a
secondary column. NULL reads as "unknown" in the UI rather than a wrong
zero, and rows fill in as queries run again.

Revision ID: a1b2c3d4e5f6
Revises: ef69f52bc770
Create Date: 2026-09-14
"""
import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "ef69f52bc770"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("query_results", sa.Column("row_count", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("query_results", "row_count")
