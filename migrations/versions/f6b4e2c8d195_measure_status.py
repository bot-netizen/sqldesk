"""Three states for a proposed measure, not two.

`approved` could not tell "nobody has looked at this yet" from "we looked and
it is wrong", so a measure somebody rejected came back on the worklist after
every harvest. `status` is proposed, approved or denied.

Revision ID: f6b4e2c8d195
Revises: e5c3d70a91b8
"""

import sqlalchemy as sa
from alembic import op

revision = "f6b4e2c8d195"
down_revision = "e5c3d70a91b8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "catalog_measures",
        sa.Column("status", sa.String(length=16), nullable=False, server_default="proposed"),
    )
    # Anything already agreed stays agreed; everything else is still a
    # proposal, which is what it was.
    op.execute("UPDATE catalog_measures SET status = 'approved' WHERE approved")
    op.drop_column("catalog_measures", "approved")


def downgrade():
    op.add_column(
        "catalog_measures",
        sa.Column("approved", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute("UPDATE catalog_measures SET approved = true WHERE status = 'approved'")
    op.drop_column("catalog_measures", "status")
