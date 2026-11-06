"""What a notebook cell printed, kept alongside its table.

A cell that prints its diagnostics and then shows a dataframe used to lose the
printing: the printed text was only carried when the cell produced text
*instead of* a table, which is the less common half of what `print` is for in
a notebook.

Revision ID: 4b9e2d81c705
Revises: 073f8bb38e7a
Create Date: 2026-10-30

"""

import sqlalchemy as sa
from alembic import op

revision = "4b9e2d81c705"
down_revision = "073f8bb38e7a"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("notebook_runs", sa.Column("printed", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("notebook_runs", "printed")
