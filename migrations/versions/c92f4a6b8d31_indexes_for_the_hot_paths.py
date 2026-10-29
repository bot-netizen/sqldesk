"""Index the lookups that scanned, and drop the one that was a copy

Measured on a database of ordinary size, these are the queries with no index
behind them at all:

* `queries(query_hash, data_source_id)` -- how a finished execution finds the
  other queries with the same text, to hand them the result. One scan of
  `queries` per execution.
* `queries(latest_query_data_id)` -- how the result cleanup asks whether a
  result is still somebody's latest. Asked per result, ten thousand results a
  run, every five minutes.
* `query_results(retrieved_at)` -- the cleanup's own cutoff, on the largest
  table in the database.
* `changes(object_type, object_id, id DESC)` -- a query's or dashboard's
  version history, which scanned every change ever recorded.

And `ix_query_results_query_hash` goes: `ix_query_results_lookup` starts with
the same column, so it answered everything the single-column index did, while
both were maintained on insert of the biggest rows there are.

CONCURRENTLY, because these tables are large on exactly the installs that need
the indexes, and a plain CREATE INDEX holds a write lock for the duration. That
means no transaction, hence the autocommit block.

Revision ID: c92f4a6b8d31
Revises: b7f2c04e9a18
Create Date: 2026-10-24

"""

from alembic import op

revision = "c92f4a6b8d31"
down_revision = "b7f2c04e9a18"
branch_labels = None
depends_on = None

INDEXES = (
    ("ix_queries_hash_data_source", "queries", "query_hash, data_source_id"),
    ("ix_queries_latest_query_data_id", "queries", "latest_query_data_id"),
    ("ix_query_results_retrieved_at", "query_results", "retrieved_at"),
    ("ix_changes_object_id_desc", "changes", "object_type, object_id, id DESC"),
)


def upgrade():
    with op.get_context().autocommit_block():
        for name, table, columns in INDEXES:
            op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS {} ON {} ({})".format(name, table, columns))
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_query_results_query_hash")


def downgrade():
    with op.get_context().autocommit_block():
        op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_query_results_query_hash ON query_results (query_hash)")
        for name, _table, _columns in INDEXES:
            op.execute("DROP INDEX CONCURRENTLY IF EXISTS {}".format(name))
