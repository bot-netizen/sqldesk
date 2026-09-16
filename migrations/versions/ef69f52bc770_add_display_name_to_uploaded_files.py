"""Add display_name to uploaded_files

Revision ID: ef69f52bc770
Revises: c8eb954aadc3
Create Date: 2026-09-13 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "ef69f52bc770"
down_revision = "c8eb954aadc3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("uploaded_files", sa.Column("display_name", sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column("uploaded_files", "display_name")
