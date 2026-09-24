import io
import os
import re
from contextlib import redirect_stdout

from alembic.config import Config
from alembic.script import ScriptDirectory

from sqldesk.models import db
from tests import BaseTestCase


def test_only_single_head_revision_in_migrations():
    """
    If multiple developers are working on migrations and one of them is merged before the
    other you might end up with multiple heads (multiple revisions with the same down_revision).

    This makes sure that there is only a single head revision in the migrations directory.

    Adopted from https://blog.jerrycodes.com/multiple-heads-in-alembic-migrations/.
    """
    config = Config(os.path.join("migrations", "alembic.ini"))
    config.set_main_option("script_location", "migrations")
    script = ScriptDirectory.from_config(config)

    # This will raise if there are multiple heads
    script.get_current_head()


#: Migrations that read the database while they run, and so cannot be
#: compiled without one. All of them are inherited from Redash; every
#: migration written since has to compile, which is what the tests below are
#: for. Adding to this list is a decision, not a fix.
NEEDS_A_LIVE_DATABASE = {
    "0f740a081d20",
    "1038c2174f5d",
    "5ec5c84ba61e",
    "640888ce445d",
    "6b5be7e0a0ef",
    "73beceabb948",
    "89bc7873a3e0",
    "969126bd800f",
    "98af61feea92",
    "9e8c841d1a30",
    "d7d747033183",
    "e7004224f284",
}

INDEX_STATEMENT = re.compile(r"^(CREATE|DROP)\s+(UNIQUE\s+)?INDEX\b", re.IGNORECASE)


def _offline_sql(config, command_name, spec):
    """The statements a migration would run, without running them."""
    from alembic import command

    out = io.StringIO()
    with redirect_stdout(out):
        getattr(command, command_name)(config, spec, sql=True)

    statements = []
    for raw in out.getvalue().split(";"):
        body = "\n".join(line for line in raw.splitlines() if not line.strip().startswith("--")).strip()
        # alembic wraps the run and stamps the version itself; neither is the
        # migration's own work.
        if body and body.upper() not in ("BEGIN", "COMMIT") and "alembic_version" not in body:
            statements.append(body)
    return statements


def _each_migration(config):
    script = ScriptDirectory.from_config(config)
    for revision in script.walk_revisions():
        if revision.down_revision is None or revision.revision in NEEDS_A_LIVE_DATABASE:
            continue
        down = revision.down_revision
        yield revision.revision, (down[0] if isinstance(down, tuple) else down)


class MigrationsTest(BaseTestCase):
    """
    Migrations are never replayed by this suite: the schema is built with
    `create_all` and stamped at head. So a migration whose SQL is wrong fails
    on nobody's machine until it meets a database -- which is how
    `a3f5c07be41d` shipped with `op.inline_literal` where it wanted
    `sa.text`, writing a partial index's predicate as a quoted string that
    Postgres rejects as a boolean. The whole suite was green; the first real
    `db upgrade` was not.
    """

    def _config(self):
        return self.app.extensions["migrate"].migrate.get_config(None)

    def test_every_migration_compiles(self):
        """The cheap half: anything that will not compile raises here."""
        config = self._config()
        compiled = 0
        for revision, down in _each_migration(config):
            _offline_sql(config, "upgrade", "{}:{}".format(down, revision))
            _offline_sql(config, "downgrade", "{}:{}".format(revision, down))
            compiled += 1

        # A guard on the guard: an exclusion list that grew to cover
        # everything would leave this passing while checking nothing.
        self.assertGreater(compiled, 10)

    def test_index_migrations_are_run_against_postgres(self):
        """
        The half that catches SQL a database rejects rather than a compiler.

        Compiling is not enough: `op.inline_literal` produces a perfectly
        valid quoted string, and only Postgres knows a partial index's
        predicate has to be a boolean. So every migration that does nothing
        but add or drop indexes -- which is safe to undo and redo -- is
        actually executed here, on the schema `create_all` just built.
        """
        config = self._config()
        run = 0
        for revision, down in _each_migration(config):
            up = _offline_sql(config, "upgrade", "{}:{}".format(down, revision))
            back = _offline_sql(config, "downgrade", "{}:{}".format(revision, down))
            statements = up + back
            if not up or not all(INDEX_STATEMENT.match(s) for s in statements):
                continue
            # `CREATE INDEX CONCURRENTLY` cannot run inside a transaction, and
            # a test that ran it outside one would leave the index behind.
            if any("CONCURRENTLY" in s.upper() for s in statements):
                continue

            # The index is already there, because `create_all` reads the same
            # model metadata the migration was written from. Take it away and
            # put it back, which runs both halves.
            for statement in back + up:
                db.session.execute(statement)
            db.session.commit()
            run += 1

        self.assertGreater(run, 0, "no index migration was executed")
