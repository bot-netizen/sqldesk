"""How a stream's consumer reads, and how it looks to the broker

Until now every stream joined a consumer group named `sqldesk-stream-<id>` and
never committed an offset. To a lag-monitoring script that is a live group with
no position at all, and it alarms on it.

The default becomes no group the broker can see: the consumer assigns itself
the partitions and commits nothing. A name, saving the position and where to
start from are each a choice somebody makes per topic.

Every existing stream gets the default, which is the fix: their groups stop
appearing on the broker without anybody having to do anything.

Revision ID: f2c6b8e41d93
Revises: a1c7f30e95bd
Create Date: 2026-10-18

"""

import sqlalchemy as sa
from alembic import op

revision = "f2c6b8e41d93"
down_revision = "a1c7f30e95bd"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("streams", sa.Column("consumer_group", sa.String(length=249), nullable=True))
    op.add_column(
        "streams", sa.Column("save_position", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column(
        "streams", sa.Column("start_from", sa.String(length=16), nullable=False, server_default="latest")
    )


def downgrade():
    op.drop_column("streams", "start_from")
    op.drop_column("streams", "save_position")
    op.drop_column("streams", "consumer_group")
