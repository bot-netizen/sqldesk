"""A catalog table can be hidden

From the catalog page and from what MCP offers a model. A Mimir cluster has
hundreds of metrics, and a list of all of them is noise to a person and to an
agent. Hiding is not access control: the table can still be queried.

Revision ID: a9d4e7c13b25
Revises: f2c6b8e41d93
Create Date: 2026-10-18

"""

import sqlalchemy as sa
from alembic import op

revision = "a9d4e7c13b25"
down_revision = "f2c6b8e41d93"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("catalog_tables", sa.Column("hidden", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column("catalog_tables", "hidden")
