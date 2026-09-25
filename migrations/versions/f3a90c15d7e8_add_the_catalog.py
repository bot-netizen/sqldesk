"""The catalog: what each table is, and what anyone does with it

Today's schema cache is a JSON blob in Redis with a TTL. You cannot search it,
join against it or ask which tables are used together, which is everything the
AI surfaces need to ask. This is the same knowledge in a shape those questions
can be asked of, plus what the query log says about usage.

A derived index, not a system of record: every row can be dropped and rebuilt
from the data source and the saved queries.

Revision ID: f3a90c15d7e8
Revises: d2b81f4a7c65
Create Date: 2026-09-25 00:20:00.000000

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f3a90c15d7e8"
down_revision = "d2b81f4a7c65"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "catalog_tables",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("org_id", sa.Integer(), nullable=True),
        sa.Column("data_source_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=1024), nullable=True),
        sa.Column("properties", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("usage_count", sa.Integer(), nullable=True),
        sa.Column("card", sa.Text(), nullable=True),
        sa.Column("harvested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_sources.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_catalog_tables_source_name", "catalog_tables", ["data_source_id", "name"], unique=True)

    op.create_table(
        "catalog_columns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("catalog_table_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=1024), nullable=True),
        sa.Column("type", sa.String(length=255), nullable=True),
        sa.Column("usage_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["catalog_table_id"], ["catalog_tables.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_catalog_columns_table_name", "catalog_columns", ["catalog_table_id", "name"], unique=True)

    op.create_table(
        "catalog_relationships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("org_id", sa.Integer(), nullable=True),
        sa.Column("data_source_id", sa.Integer(), nullable=True),
        sa.Column("left_table", sa.String(length=1024), nullable=True),
        sa.Column("left_column", sa.String(length=1024), nullable=True),
        sa.Column("right_table", sa.String(length=1024), nullable=True),
        sa.Column("right_column", sa.String(length=1024), nullable=True),
        sa.Column("observed_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_sources.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    # The harvester writes these with ON CONFLICT DO UPDATE, so this index is
    # not an optimization -- the upsert names it and fails without it.
    op.create_index(
        "ix_catalog_relationships_edge",
        "catalog_relationships",
        ["data_source_id", "left_table", "left_column", "right_table", "right_column"],
        unique=True,
    )


def downgrade():
    op.drop_index("ix_catalog_relationships_edge", table_name="catalog_relationships")
    op.drop_table("catalog_relationships")
    op.drop_index("ix_catalog_columns_table_name", table_name="catalog_columns")
    op.drop_table("catalog_columns")
    op.drop_index("ix_catalog_tables_source_name", table_name="catalog_tables")
    op.drop_table("catalog_tables")
