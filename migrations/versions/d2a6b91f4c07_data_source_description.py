"""A description on a data source.

The one piece of context that applies to every question asked of a source --
which tables to prefer, what is untrusted, what a row means -- and there was
nowhere to write it.

Revision ID: d2a6b91f4c07
Revises: c7d1e4a9b350
"""

import sqlalchemy as sa
from alembic import op

revision = "d2a6b91f4c07"
down_revision = "c7d1e4a9b350"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("data_sources", sa.Column("description", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("data_sources", "description")
