"""Who described a table, and who proposed and reviewed a measure

An agent writes descriptions and proposes measures far faster than a person
does, and "mcp" in description_source says only that a machine typed it. The
first question asked about a wrong description is whose key wrote it, and the
first question a curator asks about a measure is who is asking -- neither was
answerable without reading the event log, which no tool can return beside the
row it belongs to.

Revision ID: b7f2c04e9a18
Revises: e5c1a9b3d7f2
Create Date: 2026-10-24

"""

import sqlalchemy as sa
from alembic import op

revision = "b7f2c04e9a18"
down_revision = "e5c1a9b3d7f2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("catalog_tables", sa.Column("described_by_id", sa.Integer(), nullable=True))
    op.add_column("catalog_tables", sa.Column("described_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "catalog_tables_described_by_id_fkey", "catalog_tables", "users", ["described_by_id"], ["id"]
    )

    op.add_column("catalog_measures", sa.Column("proposed_by_id", sa.Integer(), nullable=True))
    op.add_column("catalog_measures", sa.Column("reviewed_by_id", sa.Integer(), nullable=True))
    op.add_column("catalog_measures", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "catalog_measures_proposed_by_id_fkey", "catalog_measures", "users", ["proposed_by_id"], ["id"]
    )
    op.create_foreign_key(
        "catalog_measures_reviewed_by_id_fkey", "catalog_measures", "users", ["reviewed_by_id"], ["id"]
    )


def downgrade():
    op.drop_constraint("catalog_measures_reviewed_by_id_fkey", "catalog_measures", type_="foreignkey")
    op.drop_constraint("catalog_measures_proposed_by_id_fkey", "catalog_measures", type_="foreignkey")
    op.drop_column("catalog_measures", "reviewed_at")
    op.drop_column("catalog_measures", "reviewed_by_id")
    op.drop_column("catalog_measures", "proposed_by_id")

    op.drop_constraint("catalog_tables_described_by_id_fkey", "catalog_tables", type_="foreignkey")
    op.drop_column("catalog_tables", "described_at")
    op.drop_column("catalog_tables", "described_by_id")
