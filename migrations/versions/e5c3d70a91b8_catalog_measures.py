"""Measures mined from saved queries.

The one part of a semantic layer that can be found rather than asked for:
`SUM(amount) AS gross_revenue` in a saved query is somebody naming a metric.
Proposed rather than believed -- `approved` is what a person sets, and
nothing without it reaches a model or an export.

Revision ID: e5c3d70a91b8
Revises: d2a6b91f4c07
"""

import sqlalchemy as sa
from alembic import op

revision = "e5c3d70a91b8"
down_revision = "d2a6b91f4c07"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "catalog_measures",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        # Not null, matching the model. `Column` in sqldesk.models.base is a
        # partial with nullable=False, so a migration that writes nullable=True
        # out of habit describes a different table from the one the code
        # believes in -- which is true of the catalog's first migration and is
        # not repeated here.
        sa.Column("org_id", sa.Integer(), nullable=False),
        sa.Column("data_source_id", sa.Integer(), nullable=False),
        sa.Column("table_name", sa.String(length=1024), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("column_name", sa.String(length=1024), nullable=False),
        sa.Column("usage_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("approved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("description", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_sources.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "catalog_measures_source_table_name",
        "catalog_measures",
        ["data_source_id", "table_name", "name"],
        unique=True,
    )


def downgrade():
    op.drop_index("catalog_measures_source_table_name", table_name="catalog_measures")
    op.drop_table("catalog_measures")
