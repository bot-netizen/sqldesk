"""
The two things DuckDB 2.0 changed underneath us.

Both are about somebody else's data rather than our code: a file the previous
release can still open, and a query that still parses. Neither is checked by
anything else in the suite, and both would fail silently -- a stream store
that only turns out to be unreadable when somebody rolls back, and a saved
query that only breaks when its owner next runs it.
"""

import os
import tempfile
from unittest import TestCase, mock

import duckdb

from sqldesk import settings
from sqldesk.query_runner import LEGACY_LAMBDA, storage_config
from sqldesk.query_runner.duckdb import DuckDB
from sqldesk.streams.store import Store

#: What 0.7.10 shipped, and therefore what a file we write has to stay
#: readable by. DuckDB reports its own ceiling in the refusal, so the test
#: below asserts on behaviour rather than on this number.
PREVIOUS_RELEASE = "v1.5.0"


class TestStorageConfig(TestCase):
    def test_asks_for_the_older_format_by_default(self):
        self.assertEqual(storage_config(), {"storage_compatibility_version": PREVIOUS_RELEASE})

    def test_latest_means_no_setting_at_all(self):
        # An install that will never roll back opts out, and then DuckDB is
        # left on its own default rather than being pinned to anything.
        with mock.patch.object(settings, "DUCKDB_STORAGE_COMPATIBILITY", "latest"):
            self.assertEqual(storage_config(), {})

    def test_an_empty_setting_is_not_passed_as_one(self):
        # `SQLDESK_DUCKDB_STORAGE_COMPATIBILITY=` in a .env file is how an
        # operator accidentally sets this to the empty string, and passing
        # that to DuckDB is an error rather than a default.
        with mock.patch.object(settings, "DUCKDB_STORAGE_COMPATIBILITY", "  "):
            self.assertEqual(storage_config(), {})

    def test_the_format_it_asks_for_is_one_duckdb_accepts(self):
        # The setting is a string we hand to DuckDB; a typo in it would
        # otherwise surface as every stream store failing to open.
        con = duckdb.connect(":memory:", config=storage_config())
        self.assertEqual(con.execute("SELECT 1").fetchone()[0], 1)


class TestAFileStaysReadable(TestCase):
    """
    The property that matters: 2.0 writes files 1.5.6 cannot read, unless
    told otherwise. These assert the telling works.
    """

    def _write(self, path, config):
        con = duckdb.connect(path, config=config)
        con.execute("CREATE TABLE events (id INTEGER)")
        con.execute("INSERT INTO events VALUES (1)")
        con.close()

    #: The highest storage version DuckDB 1.5.6 -- what 0.7.10 shipped --
    #: will open. It says so itself when it refuses one: "we can only read
    #: versions between 64 and 68".
    READABLE_BY_0_7 = 68

    def _storage_version(self, path):
        """
        The storage version in a DuckDB file's header.

        Bytes 8-11 are the magic `DUCK`, and the version is the little-endian
        number straight after it. Read from the file rather than asked of
        DuckDB, because the only DuckDB installed here is the new one and it
        opens everything -- so nothing it says could fail this test.
        """
        with open(path, "rb") as handle:
            head = handle.read(20)
        self.assertEqual(head[8:12], b"DUCK", "not a DuckDB file header")
        return int.from_bytes(head[12:20], "little")

    def test_our_config_writes_a_version_the_previous_release_opens(self):
        folder = tempfile.mkdtemp()
        ours = os.path.join(folder, "ours.duckdb")
        self._write(ours, storage_config())
        self.assertLessEqual(
            self._storage_version(ours),
            self.READABLE_BY_0_7,
            "a file this release writes could not be opened by 0.7.10",
        )

    def test_the_default_would_not_have(self):
        # Guards the premise, and is the reason the setting exists. If a
        # future DuckDB stops writing a format the old one refuses, this
        # fails -- and somebody should then be told the setting can go,
        # rather than left carrying it for ever.
        folder = tempfile.mkdtemp()
        latest = os.path.join(folder, "latest.duckdb")
        self._write(latest, {})
        self.assertGreater(
            self._storage_version(latest),
            self.READABLE_BY_0_7,
            "DuckDB's default now writes a format 0.7.10 can read; "
            "DUCKDB_STORAGE_COMPATIBILITY may no longer be needed.",
        )


class TestSingleArrowLambdas(TestCase):
    """
    `list_transform(l, x -> x * 2)` ran in every DuckDB before 2.0. A saved
    query using it is not ours to break on its owner's behalf.
    """

    LEGACY = "SELECT list_transform([1,2,3], x -> x * 2) AS doubled"
    CURRENT = "SELECT list_transform([1,2,3], lambda x: x * 2) AS doubled"

    def test_a_bare_connection_refuses_the_old_syntax(self):
        # The premise. When this starts failing, DuckDB has either restored
        # the syntax or removed the flag, and the shim can go.
        with self.assertRaises(Exception):
            duckdb.connect(":memory:").execute(self.LEGACY).fetchone()

    def test_the_shim_restores_it(self):
        con = duckdb.connect(":memory:")
        con.execute(LEGACY_LAMBDA)
        self.assertEqual(con.execute(self.LEGACY).fetchone()[0], [2, 4, 6])

    def test_an_uploads_connection_accepts_both_syntaxes(self):
        # Through the real runner, because the order matters: the shim has to
        # be applied before `lock_configuration`, and nothing but running it
        # proves that it was.
        runner = DuckDB({"dbpath": ":memory:"})
        con = runner._open_connection()
        self.assertEqual(con.execute(self.LEGACY).fetchone()[0], [2, 4, 6])
        self.assertEqual(con.execute(self.CURRENT).fetchone()[0], [2, 4, 6])

    def test_a_stream_store_accepts_both_syntaxes(self):
        folder = tempfile.mkdtemp()
        store = Store(os.path.join(folder, "stream-1.duckdb"))
        con = store.connection
        self.assertEqual(con.execute(self.LEGACY).fetchone()[0], [2, 4, 6])
        self.assertEqual(con.execute(self.CURRENT).fetchone()[0], [2, 4, 6])
        store.close()

    def test_the_uploads_runner_still_opens_without_the_flag(self):
        # DuckDB 2.1 removes the flag. An upload is perfectly queryable
        # without it, so a rejected SET must not be what stops the connection
        # opening -- which is exactly what a bare `con.execute` would do.
        runner = DuckDB({"dbpath": ":memory:"})
        with mock.patch("sqldesk.query_runner.duckdb.LEGACY_LAMBDA", "SET no_such_option = 'x'"):
            con = runner._open_connection()
        self.assertEqual(con.execute("SELECT 1").fetchone()[0], 1)
