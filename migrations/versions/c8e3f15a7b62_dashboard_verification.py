"""A dashboard can be verified, with a note on what was checked

Who verified it, when, and what they checked -- the same three things a
verified query records -- plus a fingerprint of the widgets and their queries
at that moment, so the page can say when the dashboard has changed since.

Revision ID: c8e3f15a7b62
Revises: a9d4e7c13b25
Create Date: 2026-10-18

"""

import sqlalchemy as sa
from alembic import op

revision = "c8e3f15a7b62"
down_revision = "a9d4e7c13b25"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("dashboards", sa.Column("verified_by_id", sa.Integer(), nullable=True))
    op.add_column("dashboards", sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("dashboards", sa.Column("verified_note", sa.Text(), nullable=True))
    op.add_column("dashboards", sa.Column("verified_fingerprint", sa.String(length=32), nullable=True))
    op.create_foreign_key(
        "dashboards_verified_by_id_fkey", "dashboards", "users", ["verified_by_id"], ["id"], ondelete="SET NULL"
    )


def downgrade():
    op.drop_constraint("dashboards_verified_by_id_fkey", "dashboards", type_="foreignkey")
    op.drop_column("dashboards", "verified_fingerprint")
    op.drop_column("dashboards", "verified_note")
    op.drop_column("dashboards", "verified_at")
    op.drop_column("dashboards", "verified_by_id")
