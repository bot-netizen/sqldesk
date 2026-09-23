"""Index query_results for the lookup get_latest actually does

`QueryResult.get_latest` filters on `query_hash` **and** `data_source`, then
takes the newest by `retrieved_at`. The only index was on `query_hash` alone,
so Postgres found every result for that hash, filtered them by data source,
and sorted what was left.

Measured on a small instance, 4,933 rows with ~65 sharing a hash: 20 buffers,
0.392 ms, with a top-N heapsort in the plan. With
`(query_hash, data_source_id, retrieved_at DESC)` -- which is the predicate
followed by the ordering -- it is a plain index scan, 7 buffers, 0.161 ms, and
the sort disappears. The timings are small here because the table is; the sort
is what grows with the number of results kept per query, and this runs on
every cache lookup.

The existing `ix_query_results_query_hash` stays. It is a prefix of this one
and so redundant for lookups, but `query_hash` alone is used elsewhere and
dropping an index is not this migration's business.

Revision ID: c4a71d9e2f18
Revises: b8f3c5d21a07
Create Date: 2026-09-23

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "c4a71d9e2f18"
down_revision = "b8f3c5d21a07"
branch_labels = None
depends_on = None

INDEX_NAME = "ix_query_results_lookup"


def upgrade():
    op.create_index(
        INDEX_NAME,
        "query_results",
        ["query_hash", "data_source_id", "retrieved_at"],
        postgresql_ops={"retrieved_at": "DESC"},
    )


def downgrade():
    op.drop_index(INDEX_NAME, table_name="query_results")
