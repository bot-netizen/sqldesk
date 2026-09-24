"""Double every widget's position for the twenty-four column grid

The grid went from twelve columns and 50px rows to twenty-four and 25px, and
every number the *frontend* refers to doubled with it. The numbers already in
the database did not: a widget saved as six columns wide was half a screen on
the old grid and is a quarter of one on this grid, and a widget three rows
tall lost half its height. Every dashboard built before the change renders
shrunken until this runs.

Upstream shipped the same migration when they went from six columns to twelve
(db0aca1ebd32); that one doubled `col` and `sizeX`. This one also doubles
`row` and `sizeY`, because the row height halved as well as the column width.

Guarded on the value being an integer. `jsonb_set` returns NULL if any
argument is NULL, so a widget with no position -- or with a position missing
one of these keys -- would have its whole `options` wiped, taking its
parameter mappings with it. The upstream migration has that hole; this one
does not.

A negative `sizeY` means the widget sizes itself to its contents, and doubling
keeps it negative, so those are left to go on meaning what they meant.

Revision ID: c9f1a67b3d84
Revises: a3f5c07be41d
Create Date: 2026-09-24 22:45:00.000000

"""
from alembic import op

revision = "c9f1a67b3d84"
down_revision = "a3f5c07be41d"
branch_labels = None
depends_on = None

KEYS = ("col", "row", "sizeX", "sizeY")


def _scale(expression):
    for key in KEYS:
        op.execute(
            """
            UPDATE widgets
            SET options = jsonb_set(
                    options,
                    '{{position,{key}}}',
                    to_jsonb(({expression})::int)
                )
            WHERE options -> 'position' ->> '{key}' ~ '^-?[0-9]+$'
            """.format(key=key, expression=expression.format(key=key))
        )


def upgrade():
    _scale("(options -> 'position' ->> '{key}')::int * 2")


def downgrade():
    # Integer division, not a multiply by 0.5, which would write 3.0 where the
    # column held 3. Every value `upgrade` wrote is even, so this is exact.
    _scale("(options -> 'position' ->> '{key}')::int / 2")
