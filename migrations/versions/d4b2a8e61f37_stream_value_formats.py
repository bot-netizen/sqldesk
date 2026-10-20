"""A stream can read Avro and Protobuf, not only JSON

How a topic's messages are read -- `auto`, which handles JSON and anything with
a schema registry header, or `avro` / `protobuf` with uploaded schema files --
the files themselves, and which message in them a topic carries. Every existing
stream is `auto`, which reads JSON exactly as before.

Revision ID: d4b2a8e61f37
Revises: c8e3f15a7b62
Create Date: 2026-10-20

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d4b2a8e61f37"
down_revision = "c8e3f15a7b62"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("streams", sa.Column("value_format", sa.String(length=16), nullable=False, server_default="auto"))
    op.add_column("streams", sa.Column("value_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("streams", sa.Column("message_type", sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column("streams", "message_type")
    op.drop_column("streams", "value_schema")
    op.drop_column("streams", "value_format")
