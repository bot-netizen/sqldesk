from unittest import TestCase

from tealdash.query_runner.duckdb import DuckDB, enabled


class DuckDBConnectionCacheTest(TestCase):
    """DataSource.query_runner is a property, so a runner is built per access.

    Without caching that meant a fresh connect plus an INSTALL/LOAD per
    extension on every query.
    """

    def setUp(self):
        if not enabled:
            self.skipTest("duckdb is not installed")
        DuckDB._connections.clear()

    def tearDown(self):
        DuckDB._connections.clear()

    def test_same_configuration_reuses_one_connection(self):
        a = DuckDB({"dbpath": ":memory:"})
        b = DuckDB({"dbpath": ":memory:"})
        self.assertIs(a.con, b.con)

    def test_different_configurations_do_not_share(self):
        a = DuckDB({"dbpath": ":memory:"})
        b = DuckDB({"dbpath": ":memory:", "extensions": "json"})
        self.assertIsNot(a.con, b.con)

    def test_a_dead_connection_is_replaced_rather_than_reused(self):
        first = DuckDB({"dbpath": ":memory:"})
        dead = first.con
        dead.close()

        second = DuckDB({"dbpath": ":memory:"})
        self.assertIsNot(second.con, dead)
        self.assertEqual(second.con.execute("SELECT 1").fetchone()[0], 1)

    def test_queries_still_work_through_a_reused_connection(self):
        DuckDB({"dbpath": ":memory:"})
        runner = DuckDB({"dbpath": ":memory:"})
        data, error = runner.run_query("SELECT 42 AS answer", None)
        self.assertIsNone(error)
        self.assertEqual(data["rows"], [{"answer": 42}])
