"""Move saved charts from the "Tealdash" palette name to "SQLDesk"

The default palette is named after the product, and the product has been renamed
again. c3e9a1f5d7b2 did this once already, from "Redash" to "Tealdash"; this is
the same move one step along.

Charts are not broken without it -- resolveColorScheme in viz-lib treats both
former names as aliases of the default, which is what stops an unknown palette
taking down the dashboard a chart sits on. This is here so the stored value says
what the editor shows, rather than relying on the alias forever.

The downgrade only understands "SQLDesk", and current code resolves both former
names to the same palette, so a chart that was already "Tealdash" before the
upgrade comes back as "Tealdash" and looks no different either way.

Revision ID: a8e1d0c4b726
Revises: f4b2c8d1e903
Create Date: 2026-09-17

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "a8e1d0c4b726"
down_revision = "f4b2c8d1e903"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        UPDATE visualizations
        SET options = jsonb_set(options, '{color_scheme}', '"SQLDesk"')
        WHERE options->>'color_scheme' = 'Tealdash'
        """
    )


def downgrade():
    op.execute(
        """
        UPDATE visualizations
        SET options = jsonb_set(options, '{color_scheme}', '"Tealdash"')
        WHERE options->>'color_scheme' = 'SQLDesk'
        """
    )
