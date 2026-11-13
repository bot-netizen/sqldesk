"""An alert's history says what each destination did

`alert_fires.deliveries`: one entry per destination the alert was sent to
when it changed state -- its name, whether it went, and if not, why. Null for
an event that sent nothing (muted, or settling from unknown) and for every
event recorded before this.

Revision ID: b2f6d9e4a1c7
Revises: d7e3ae10b9a9
Create Date: 2026-11-13

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b2f6d9e4a1c7"
down_revision = "d7e3ae10b9a9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("alert_fires", sa.Column("deliveries", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade():
    op.drop_column("alert_fires", "deliveries")
