"""Rename the legacy chart colour scheme

Chart options persist the colour scheme by name, and the default palette was
renamed from "Redash" to "Tealdash". Every chart saved before that still says
"Redash", which the renamed palette map no longer contained -- the lookup
returned undefined and rendering threw, taking the whole dashboard with it.

The frontend now resolves legacy and unknown names on its own, so this is not
what fixes the crash. It is here so the stored data says what the product calls
the palette, and so nothing downstream -- exports, the API, anything reading
visualizations.options directly -- has to know about the old name.

The downgrade is the exact inverse and is safe to run: code from before the
rename only understands "Redash", and current code resolves "Redash" to the same
palette, so the only thing it changes is the label on identical colours.

Revision ID: c3e9a1f5d7b2
Revises: b7c1e4d92f08
Create Date: 2026-09-15

"""

from alembic import op

revision = "c3e9a1f5d7b2"
down_revision = "b7c1e4d92f08"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        UPDATE visualizations
        SET options = jsonb_set(options, '{color_scheme}', '"Tealdash"')
        WHERE options->>'color_scheme' = 'Redash'
        """
    )


def downgrade():
    op.execute(
        """
        UPDATE visualizations
        SET options = jsonb_set(options, '{color_scheme}', '"Redash"')
        WHERE options->>'color_scheme' = 'Tealdash'
        """
    )
