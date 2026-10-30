"""
A notebook's handoff file: what a cell hands over, and what it cannot reach.

Two claims this suite exists to hold up.

**The handoff keeps its types.** A column the query runner called a datetime
comes back a timestamp, and a column that happened to be all null in this run
is still the type it was declared -- which is the difference between the next
cell's join working and failing for a reason that has nothing to do with the
data.

**A cell's own SQL cannot read the machine.** The store is sealed before user
SQL runs, and the test for that is a statement that tries to read a file which
really exists.
"""

import os
import shutil
import tempfile
from unittest import TestCase, mock

from sqldesk.notebooks.store import Store, TooMuch
from sqldesk.query_runner import (
    TYPE_BOOLEAN,
    TYPE_DATE,
    TYPE_DATETIME,
    TYPE_FLOAT,
    TYPE_INTEGER,
    TYPE_STRING,
)


def columns(*pairs):
    """Columns in the shape a query runner reports them."""
    return [{"name": name, "friendly_name": name, "type": type_} for name, type_ in pairs]


class StoreTestCase(TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.store = Store(os.path.join(self.directory, "notebook-1.duckdb"))

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.directory, ignore_errors=True)

    def declared_type(self, table, column):
        found = self.store.connection.execute(
            "SELECT data_type FROM duckdb_columns() WHERE table_name = ? AND column_name = ?",
            [table, column],
        ).fetchone()
        return found[0]


class TestAHandoff(StoreTestCase):
    def test_a_cell_hands_over_its_rows(self):
        written = self.store.hand_off(
            "orders",
            columns(("id", TYPE_INTEGER), ("customer", TYPE_STRING)),
            [{"id": 1, "customer": "Ada"}, {"id": 2, "customer": "Grace"}],
        )

        self.assertEqual(2, written)
        self.assertEqual(2, self.store.row_count("orders"))
        self.assertEqual(["orders"], self.store.names())

    def test_the_next_cell_sees_it_as_a_relation(self):
        self.store.hand_off(
            "orders",
            columns(("id", TYPE_INTEGER), ("total", TYPE_FLOAT)),
            [{"id": 1, "total": 10.5}, {"id": 2, "total": 4.5}],
        )

        _, rows = self.store.select("SELECT sum(total) AS t FROM orders")

        self.assertEqual(15.0, rows[0]["t"])

    def test_every_runner_type_lands_as_the_type_it_was_declared(self):
        self.store.hand_off(
            "everything",
            columns(
                ("n", TYPE_INTEGER),
                ("f", TYPE_FLOAT),
                ("b", TYPE_BOOLEAN),
                ("s", TYPE_STRING),
                ("d", TYPE_DATE),
                ("t", TYPE_DATETIME),
            ),
            [{"n": 1, "f": 1.5, "b": True, "s": "x", "d": "2026-10-30", "t": "2026-10-30T09:00:00+00:00"}],
        )

        self.assertEqual("BIGINT", self.declared_type("everything", "n"))
        self.assertEqual("DOUBLE", self.declared_type("everything", "f"))
        self.assertEqual("BOOLEAN", self.declared_type("everything", "b"))
        self.assertEqual("VARCHAR", self.declared_type("everything", "s"))
        self.assertEqual("DATE", self.declared_type("everything", "d"))
        self.assertEqual("TIMESTAMP WITH TIME ZONE", self.declared_type("everything", "t"))

    def test_a_column_that_is_all_null_keeps_its_type(self):
        """
        The reason the types are declared rather than inferred. `read_json_auto`
        guesses from the values present, so this column would come back VARCHAR
        and the next cell's arithmetic would fail on data that is fine.
        """
        self.store.hand_off(
            "sparse",
            columns(("id", TYPE_INTEGER), ("amount", TYPE_FLOAT)),
            [{"id": 1, "amount": None}, {"id": 2, "amount": None}],
        )

        self.assertEqual("DOUBLE", self.declared_type("sparse", "amount"))
        _, rows = self.store.select("SELECT coalesce(sum(amount), 0) AS t FROM sparse")
        self.assertEqual(0, rows[0]["t"])

    def test_re_running_a_cell_replaces_what_it_handed_over(self):
        where = columns(("id", TYPE_INTEGER))
        self.store.hand_off("orders", where, [{"id": 1}])
        self.store.hand_off("orders", where, [{"id": 7}, {"id": 8}])

        _, rows = self.store.select("SELECT id FROM orders ORDER BY id")

        self.assertEqual([7, 8], [row["id"] for row in rows])

    def test_the_scratch_file_does_not_outlive_the_write(self):
        """
        It is written inside the sandbox a cell's SQL may read, so leaving one
        behind would hand the next cell somebody else's rows.
        """
        self.store.hand_off("orders", columns(("id", TYPE_INTEGER)), [{"id": 1}])

        left = [name for name in os.listdir(self.directory) if "handoff.json" in name]

        self.assertEqual([], left, "a cell sealed into this directory could read it")

    def test_the_first_cell_of_a_brand_new_notebook_can_write(self):
        """
        The directory does not exist until the store makes it, and `hand_off`
        writes a scratch file into it -- so getting that order wrong fails on a
        notebook's very first cell and nowhere else.
        """
        fresh = Store(os.path.join(self.directory, "notebook-99", "handoff.duckdb"))
        try:
            written = fresh.hand_off("orders", columns(("id", TYPE_INTEGER)), [{"id": 1}])
        finally:
            fresh.close()

        self.assertEqual(1, written)

    def test_a_result_with_no_columns_is_refused(self):
        with self.assertRaises(ValueError):
            self.store.hand_off("empty", [], [])

    def test_a_name_that_could_not_be_a_relation_is_refused(self):
        for name in ("1st", "orders; drop table orders", "", None, "two words"):
            with self.assertRaises(ValueError):
                self.store.hand_off(name, columns(("id", TYPE_INTEGER)), [{"id": 1}])


class TestTheBudget(StoreTestCase):
    """
    Three rows instead of five million, because the budget is one `if` and
    generating the real number to exercise it would make the suite slower for
    nothing.
    """

    def setUp(self):
        super().setUp()
        patched = mock.patch("sqldesk.notebooks.store.ROW_BUDGET", 3)
        patched.start()
        self.addCleanup(patched.stop)

    def test_a_cell_cannot_hand_over_more_than_the_budget(self):
        with self.assertRaises(TooMuch) as caught:
            self.store.hand_off("big", columns(("id", TYPE_INTEGER)), ({"id": n} for n in range(10)))

        self.assertIn("3", str(caught.exception))
        # And the half-written table is not left looking like a result.
        self.assertFalse(self.store.has("big"))

    def test_exactly_the_budget_is_allowed(self):
        written = self.store.hand_off("exact", columns(("id", TYPE_INTEGER)), [{"id": 1}, {"id": 2}, {"id": 3}])

        self.assertEqual(3, written)


class TestTheDisplaySlice(StoreTestCase):
    def test_the_slice_says_how_much_there_really_was(self):
        self.store.hand_off("orders", columns(("id", TYPE_INTEGER)), [{"id": n} for n in range(100)])

        found, rows, total = self.store.display_slice("orders", limit=10)

        self.assertEqual(10, len(rows))
        self.assertEqual(100, total, "the page would imply ten rows was the whole result")
        self.assertEqual(["id"], [column["name"] for column in found])

    def test_the_slice_carries_the_types_the_visualization_editor_reads(self):
        self.store.hand_off(
            "orders",
            columns(("id", TYPE_INTEGER), ("at", TYPE_DATETIME)),
            [{"id": 1, "at": "2026-10-30T09:00:00+00:00"}],
        )

        found, _, _ = self.store.display_slice("orders")

        self.assertEqual({"id": TYPE_INTEGER, "at": TYPE_DATETIME}, {c["name"]: c["type"] for c in found})


class TestParquet(StoreTestCase):
    def test_a_relation_goes_out_and_comes_back_whole(self):
        """
        How a cell's data reaches an interpreter and how its result returns.
        Parquet on both sides so a timestamp needs no agreed string format.
        """
        self.store.hand_off(
            "orders",
            columns(("id", TYPE_INTEGER), ("at", TYPE_DATETIME)),
            [{"id": 1, "at": "2026-10-30T09:00:00+00:00"}],
        )
        shipped = os.path.join(self.directory, "orders.parquet")

        self.store.export("orders", shipped)
        self.store.hand_off_parquet("returned", shipped)

        self.assertEqual("TIMESTAMP WITH TIME ZONE", self.declared_type("returned", "at"))
        _, rows = self.store.select("SELECT id FROM returned")
        self.assertEqual([1], [row["id"] for row in rows])


class TestRenaming(StoreTestCase):
    def test_renaming_a_cell_takes_its_handoff_with_it(self):
        self.store.hand_off("orders", columns(("id", TYPE_INTEGER)), [{"id": 1}])

        self.assertTrue(self.store.rename("orders", "sales"))

        self.assertEqual(["sales"], self.store.names())
        self.assertEqual(1, self.store.row_count("sales"))

    def test_renaming_a_cell_that_never_ran_is_not_an_error(self):
        self.assertFalse(self.store.rename("never_ran", "still_has_not"))


class TestSealing(StoreTestCase):
    """
    What a cell's own SQL may reach.

    Measured, not assumed, and the measurement changed the design: on 1.5.6 and
    on 2.0.0 alike, `allowed_directories` restricts nothing by itself. It is
    the carve-out from `enable_external_access = false`. So the sandbox is the
    pair of them, the sealing is what switches it on, and what stays readable
    afterwards is the notebook's own directory -- which is why a notebook has
    one to itself.

    Every file here really exists; a refusal to read a missing file would prove
    nothing.
    """

    def setUp(self):
        super().setUp()
        self.elsewhere = tempfile.mkdtemp()
        self.someone_elses = os.path.join(self.elsewhere, "secret.csv")
        with open(self.someone_elses, "w", encoding="utf-8") as handle:
            handle.write("a\n1\n")
        self.store.hand_off("orders", columns(("id", TYPE_INTEGER)), [{"id": 1}, {"id": 2}])

    def tearDown(self):
        shutil.rmtree(self.elsewhere, ignore_errors=True)
        super().tearDown()

    def read_the_secret(self):
        return self.store.select("SELECT * FROM read_csv_auto('{}')".format(self.someone_elses))

    def test_allowed_directories_alone_confines_nothing(self):
        """
        The finding this class exists for. If this ever starts failing, the
        sandbox got stronger and `run_cell_sql` can stop being the only door --
        but until then, unsealed SQL has the run of the machine.
        """
        self.assertEqual(1, len(self.read_the_secret()[1]))

    def test_a_cell_cannot_read_a_file_outside_its_notebook(self):
        self.store.seal()

        with self.assertRaises(Exception):
            self.read_the_secret()

    def test_running_a_cells_sql_seals_without_being_asked(self):
        """
        The caller cannot forget. This is the only entry point a cell's SQL
        uses, and it closes the door before the SQL runs rather than after.
        """
        self.store.run_cell_sql("SELECT 1 AS n")

        with self.assertRaises(Exception):
            self.read_the_secret()

    def test_materializing_a_cell_seals_first(self):
        """
        The path a cell's SQL really takes. `run_cell_sql` is for a cell that
        only looks; a cell that produces a handoff goes through `materialize`,
        and that is the statement with somebody else's SQL inside it.
        """
        self.store.materialize("summary", "SELECT count(*) AS n FROM orders")

        with self.assertRaises(Exception):
            self.read_the_secret()

    def test_a_cell_cannot_attach_another_notebooks_handoff(self):
        """
        Why each notebook gets a directory. A shared one would stay inside the
        carve-out, and a notebook may be built on a data source whoever opened
        this one is not permitted to see.
        """
        next_door = Store(os.path.join(os.path.dirname(self.directory), "notebook-2", "handoff.duckdb"))
        try:
            next_door.hand_off("salaries", columns(("amount", TYPE_INTEGER)), [{"amount": 90000}])
        finally:
            next_door.close()
        self.store.seal()

        with self.assertRaises(Exception):
            self.store.select("ATTACH '{}' AS theirs".format(next_door.path))

    def test_a_cell_cannot_unseal_or_widen_what_it_may_read(self):
        self.store.seal()

        with self.assertRaises(Exception):
            self.store.connection.execute("SET enable_external_access = true")
        with self.assertRaises(Exception):
            self.store.connection.execute("SET allowed_directories = ?", [[self.elsewhere + os.sep]])

    def test_sealing_leaves_the_notebook_entirely_usable(self):
        columns_found, rows = self.store.run_cell_sql("SELECT count(*) AS n FROM orders")

        self.assertEqual(2, rows[0]["n"])
        self.assertEqual(["n"], [column["name"] for column in columns_found])

    def test_we_can_still_write_our_own_files_before_sealing(self):
        self.store.export("orders", os.path.join(self.directory, "orders.parquet"))

        self.assertTrue(os.path.exists(os.path.join(self.directory, "orders.parquet")))

    def test_sealing_twice_is_not_an_error(self):
        self.store.seal()
        self.store.seal()


class TestDiscarding(StoreTestCase):
    def test_discarding_removes_the_file(self):
        self.store.hand_off("orders", columns(("id", TYPE_INTEGER)), [{"id": 1}])

        self.store.discard()

        self.assertFalse(os.path.exists(self.store.path))

    def test_discarding_twice_is_not_an_error(self):
        self.store.discard()
        self.store.discard()


class TestReadOnly(StoreTestCase):
    def test_a_read_only_store_refuses_to_write(self):
        self.store.hand_off("orders", columns(("id", TYPE_INTEGER)), [{"id": 1}])
        self.store.close()

        reader = Store(self.store.path, read_only=True)
        try:
            self.assertEqual(1, reader.row_count("orders"))
            with self.assertRaises(ValueError):
                reader.hand_off("orders", columns(("id", TYPE_INTEGER)), [{"id": 2}])
        finally:
            reader.close()
