"""A title for a notebook cell, separate from the name other cells use.

`name` is an identifier: later cells are written against it, so renaming one
breaks them. A title is prose and breaks nothing — which is what the contents
list needs, because a contents list reading `cell_1 … cell_30` is one nobody
reads.

Revision ID: 5c1f7a92b4d8
Revises: 4b9e2d81c705
Create Date: 2026-10-31

"""

import sqlalchemy as sa
from alembic import op

revision = "5c1f7a92b4d8"
down_revision = "4b9e2d81c705"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("notebook_cells", sa.Column("title", sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column("notebook_cells", "title")
