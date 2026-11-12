"""The Slack bot token is stored as bytes, where an install has it as text

`f9b3d61c48a7` created `slack_workspaces.encrypted_bot_token` as Text, and the
model's `EncryptedType` reads and writes bytes. Writing worked: psycopg2 sends
the ciphertext as a bytea literal and Postgres keeps it in the text column as
its `\\x...` hex form. Reading did not -- SQLAlchemy's LargeBinary result
processor calls `bytes()` on a str -- so once a token was saved, every query
on the table failed, and Settings -> Slack answered 500 to everybody.

Only an install whose schema went *through* `f9b3d61c48a7` has the Text
column: one made before 0.7.0 and upgraded since. A fresh install builds its
tables from the models and has always had bytea, as do the tests, which is how
it shipped.

The text in a broken row is `\\x` and the hex of the ciphertext, so decoding it
gives back the exact bytes: the token survives and nobody has to paste it
again. A Postgres whose `bytea_output` is `escape` would have written the
ciphertext's own characters instead -- a Fernet token is base64, so the same
ASCII -- and those are taken as they are.

One statement, deciding inside the database, rather than a query here first:
every migration since Redash's has to compile without a database to talk to
(tests/test_migrations.py), and on a column that is already bytea -- a fresh
install, or one fixed by hand -- it does nothing.

Revision ID: d7e3ae10b9a9
Revises: a8d3f6c1e924
Create Date: 2026-11-12

"""

import sqlalchemy as sa
from alembic import op

revision = "d7e3ae10b9a9"
down_revision = "a8d3f6c1e924"
branch_labels = None
depends_on = None


CONVERT = r"""
DO $convert$
BEGIN
    IF (
        SELECT data_type FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'slack_workspaces'
          AND column_name = 'encrypted_bot_token'
    ) = 'text' THEN
        ALTER TABLE slack_workspaces
            ALTER COLUMN encrypted_bot_token TYPE bytea
            USING CASE
                WHEN left(encrypted_bot_token, 2) = '\x'
                    THEN decode(substr(encrypted_bot_token, 3), 'hex')
                ELSE convert_to(encrypted_bot_token, 'UTF8')
            END;
    END IF;
END
$convert$
"""


def upgrade():
    op.execute(sa.text(CONVERT))


def downgrade():
    # Nothing to undo. No version of SQLDesk can read the token from a Text
    # column -- 0.8.2's model is the same EncryptedType -- so going back to
    # one would break the install this migration fixed, and `f9b3d61c48a7`
    # now creates the column as bytea anyway.
    pass
