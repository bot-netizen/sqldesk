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

    def test_the_grid_migration_doubles_positions_and_spares_everything_else(self):
        """
        `c9f1a67b3d84` rewrites live data, which makes it the one migration
        here that can destroy something rather than merely fail.

        `jsonb_set` returns NULL if any argument is NULL, so a widget with no
        `position` -- or a position missing one of the four keys -- would have
        its whole `options` replaced by NULL, taking its parameter mappings
        with it. Upstream's 6-to-12 migration has exactly that hole. This
        runs the real SQL against real rows to show that ours does not.
        """
        config = self._config()
        spec = "a3f5c07be41d:c9f1a67b3d84"
        up = _offline_sql(config, "upgrade", spec)
        down = _offline_sql(config, "downgrade", "c9f1a67b3d84:a3f5c07be41d")
        self.assertTrue(up, "the migration compiled to nothing")

        ordinary = self.factory.create_widget(
            options={
                "position": {"col": 3, "row": 4, "sizeX": 6, "sizeY": 3, "autoHeight": False},
                "parameterMappings": {"region": {"type": "dashboard-level"}},
            }
        )
        # Sizes itself to its contents; doubling has to keep it negative.
        auto = self.factory.create_widget(options={"position": {"col": 0, "row": 0, "sizeX": 6, "sizeY": -1}})
        # A textbox saved before positions existed at all.
        positionless = self.factory.create_widget(options={"parameterMappings": {}})
        db.session.commit()
        ids = (ordinary.id, auto.id, positionless.id)

        def options_of(widget_id):
            row = db.session.execute("SELECT options FROM widgets WHERE id = :id", {"id": widget_id}).scalar()
            return row

        for statement in up:
            db.session.execute(statement)
        db.session.commit()

        after = options_of(ordinary.id)["position"]
        self.assertEqual(
            {"col": 6, "row": 8, "sizeX": 12, "sizeY": 6},
            {key: after[key] for key in ("col", "row", "sizeX", "sizeY")},
        )
        self.assertFalse(after["autoHeight"], "keys it does not own should be left alone")
        self.assertEqual(
            {"region": {"type": "dashboard-level"}},
            options_of(ordinary.id)["parameterMappings"],
            "the rest of options has to survive",
        )
        self.assertEqual(-2, options_of(auto.id)["position"]["sizeY"], "auto height must stay negative")
        self.assertEqual(
            {"parameterMappings": {}}, options_of(positionless.id), "a widget with no position is not touched"
        )

        for statement in down:
            db.session.execute(statement)
        db.session.commit()

        back = options_of(ordinary.id)["position"]
        self.assertEqual(
            {"col": 3, "row": 4, "sizeX": 6, "sizeY": 3},
            {key: back[key] for key in ("col", "row", "sizeX", "sizeY")},
            "downgrade has to put back exactly what was there",
        )
        self.assertEqual(-1, options_of(auto.id)["position"]["sizeY"])
        self.assertTrue(all(options_of(i) is not None for i in ids), "no widget lost its options")

    def test_encrypted_columns_are_stored_the_way_the_existing_ones_are(self):
        """
        `EncryptedType` writes bytes. A migration that declares its
        `encrypted_options` as Text accepts every write and fails on every
        read with "string argument without an encoding" -- and passes this
        suite, because the schema here comes from `create_all` on the models
        rather than from the migrations.

        So: whatever DDL type the established encrypted columns compile to,
        any new one compiles to the same.
        """
        from sqldesk import models

        dialect = db.engine.dialect
        established = models.DataSource.__table__.c.encrypted_options.type.compile(dialect)

        for model in (models.AIProvider, models.NotificationDestination):
            column = model.__table__.c.encrypted_options
            self.assertEqual(
                established,
                column.type.compile(dialect),
                "{}.encrypted_options is {} where DataSource's is {}".format(
                    model.__tablename__, column.type.compile(dialect), established
                ),
            )
