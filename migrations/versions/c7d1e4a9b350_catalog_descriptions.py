"""Descriptions on catalog tables and columns.

Structure comes from the engine and usage comes from the query log; neither
says what a thing *means*. Several runners already return a description --
MySQL reads `table_comment` and `column_comment` today -- and the harvester
was dropping it on the floor. This is somewhere to put it, and somewhere for
a person to write one where the warehouse carries none.

`description_source` records where the sentence came from, so that a later
harvest cannot quietly replace a human's words with an engine's silence.

Revision ID: c7d1e4a9b350
Revises: b6e2f81c0a43
"""

import sqlalchemy as sa
from alembic import op

revision = "c7d1e4a9b350"
down_revision = "b6e2f81c0a43"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("catalog_tables", "catalog_columns"):
        op.add_column(table, sa.Column("description", sa.Text(), nullable=True))
        op.add_column(table, sa.Column("description_source", sa.String(length=16), nullable=True))


def downgrade():
    for table in ("catalog_tables", "catalog_columns"):
        op.drop_column(table, "description_source")
        op.drop_column(table, "description")
