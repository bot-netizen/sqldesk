"""Index query_results for the cache lookup

QueryResult.get_latest filters on query_hash, data_source_id and freshness and
then sorts on retrieved_at, but the only index covered query_hash. The planner
therefore bitmap-scanned every row that ever shared a hash, applied the other
two predicates as a heap filter, and sorted the survivors:

    Limit
      -> Sort
           Sort Key: retrieved_at DESC
           -> Bitmap Heap Scan on query_results
                Recheck Cond: query_hash = ...
                Filter: data_source_id = ... AND retrieved_at + interval >= now()
                -> Bitmap Index Scan on ix_query_results_query_hash

That work is linear in how much history a query has accumulated, and a query on
a five-minute schedule accumulates roughly 105,000 rows a year. The composite
index turns it into one descent plus LIMIT 1, with no sort and no post-filter.

retrieved_at is indexed descending to match the ORDER BY, so the first row the
index yields is the answer.

ix_query_results_query_hash goes at the same time. Every query on this table
that filters query_hash also filters data_source_id -- both QueryResult.get_latest
and Query.update_latest_result_by_query_hash -- so the composite's leading column
covers it completely, and keeping two indexes where one serves taxes every insert
on the most frequently written table in the schema.

Both operations run CONCURRENTLY: this table is large on any busy instance and a
plain CREATE INDEX would hold a write lock for the duration. That cannot run
inside a transaction, hence the autocommit block.

Measured on 100,000 rows of history for one query hash:

    before   66.734 ms   3,356 buffers   parallel scan + top-N sort
    after     0.064 ms       4 buffers   index scan, no sort

Revision ID: b7c1e4d92f08
Revises: a1b2c3d4e5f6
Create Date: 2026-09-15

"""

from alembic import op

revision = "b7c1e4d92f08"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None

INDEX_NAME = "ix_query_results_cache_lookup"
REDUNDANT_INDEX = "ix_query_results_query_hash"


def upgrade():
    with op.get_context().autocommit_block():
        op.create_index(
            INDEX_NAME,
            "query_results",
            ["query_hash", "data_source_id", "retrieved_at"],
            unique=False,
            postgresql_concurrently=True,
            postgresql_ops={"retrieved_at": "DESC"},
        )
        op.drop_index(REDUNDANT_INDEX, table_name="query_results", postgresql_concurrently=True)


def downgrade():
    with op.get_context().autocommit_block():
        op.create_index(
            REDUNDANT_INDEX,
            "query_results",
            ["query_hash"],
            unique=False,
            postgresql_concurrently=True,
        )
        op.drop_index(INDEX_NAME, table_name="query_results", postgresql_concurrently=True)
