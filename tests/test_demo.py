"""
The demo, and the one thing about it that rots.

A demo's whole value is that it covers everything. The moment a
visualization is added without one, the demo quietly stops being a demo of
"all the visualizations" and nobody finds out, because nothing fails -- the
dashboard still loads, with one chart missing that nobody was looking for.

So the catalog is read out of viz-lib and compared, and the queries are run
against the data the demo actually builds.
"""

import os
import re
import shutil
import tempfile
from unittest import TestCase, mock

from sqldesk import demo, models
from sqldesk.demo import content, data
from sqldesk.models import db
from tests import BaseTestCase

VIZ = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "viz-lib", "src", "visualizations")


def registered_types():
    """Every `type:` viz-lib registers, read from the source of truth."""
    found = set()
    for entry in os.listdir(VIZ):
        index = os.path.join(VIZ, entry, "index.ts")
        if not os.path.exists(index):
            continue
        with open(index, encoding="utf-8") as f:
            match = re.search(r'^\s*type:\s*"([A-Z_]+)"', f.read(), re.M)
        if match:
            found.add(match.group(1))
    return found


class TestTheDemoCoversEveryVisualization(TestCase):
    def test_every_registered_type_is_demonstrated(self):
        demonstrated = {type_ for _, type_, _, _ in content.VISUALIZATIONS}

        missing = registered_types() - demonstrated
        self.assertEqual(
            set(),
            missing,
            "these visualizations have no demo, so the demo no longer shows them all: {}".format(sorted(missing)),
        )

    def test_and_demonstrates_nothing_that_does_not_exist(self):
        demonstrated = {type_ for _, type_, _, _ in content.VISUALIZATIONS}

        invented = demonstrated - registered_types()
        self.assertEqual(set(), invented, "the demo names visualizations viz-lib does not have")

    def test_every_visualization_names_a_query_that_exists(self):
        named = {name for name, _, _ in content.QUERIES}

        for query_name, _, visualization, _ in content.VISUALIZATIONS:
            self.assertIn(query_name, named, "{} is built on a query the demo does not define".format(visualization))

    def test_every_widget_names_a_visualization_that_exists(self):
        made = {name for _, _, name, _ in content.VISUALIZATIONS}

        for entry in content.DASHBOARD_WIDGETS:
            self.assertIn(entry[0], made, "the dashboard places {!r}, which is not made".format(entry[0]))
            for tab in entry[2] if len(entry) > 2 else []:
                self.assertIn(tab, made, "{!r} is offered as a tab but is not made".format(tab))

    def test_every_tab_belongs_to_its_widget_s_own_query(self):
        """
        The rule that makes tabs worth having: a dashboard fetches the query
        once and draws it several ways. A tab of some *other* query would
        have to fetch, and the server drops it -- so a demo that pairs them
        across queries silently shows a widget with no tabs, which is what
        this one did.
        """
        query_of = {name: query for query, _, name, _ in content.VISUALIZATIONS}

        for entry in content.DASHBOARD_WIDGETS:
            for tab in entry[2] if len(entry) > 2 else []:
                self.assertEqual(
                    query_of[entry[0]],
                    query_of[tab],
                    "{!r} offers {!r} as a tab, but they are built on different queries".format(entry[0], tab),
                )

    def test_visualization_names_are_unique(self):
        # They are the handle the dashboard places widgets by.
        names = [name for _, _, name, _ in content.VISUALIZATIONS]

        self.assertEqual(len(names), len(set(names)))


class TestTheDemoData(TestCase):
    """
    The queries have to be valid SQL against the tables the demo builds, and
    nothing short of running them says so.
    """

    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.mkdtemp()
        cls.path = demo.build_the_data(os.path.join(cls.directory, "demo.duckdb"))
        from sqldesk.query_runner import deferred

        cls.connection = deferred("duckdb").connect(cls.path, read_only=True)

    @classmethod
    def tearDownClass(cls):
        cls.connection.close()
        shutil.rmtree(cls.directory, ignore_errors=True)

    def test_it_builds_the_tables_the_queries_read(self):
        tables = {row[0] for row in self.connection.execute("SELECT table_name FROM duckdb_tables()").fetchall()}

        self.assertEqual(
            {"places", "channels", "categories", "services", "funnel_steps", "customers", "orders", "service_days"},
            tables,
        )

    def test_every_demo_query_runs_and_returns_rows(self):
        for name, _, sql in content.QUERIES:
            with self.subTest(query=name):
                rows = self.connection.execute(sql).fetchall()
                self.assertTrue(rows, "{} returned nothing, so its chart would be blank".format(name))

    def test_the_random_columns_are_drawn_per_row(self):
        """
        One row is not a chart.

        `(SELECT x FROM t ORDER BY random() LIMIT 1)` is uncorrelated, so it
        is evaluated once for the whole statement and every row gets the same
        answer. It runs, it returns four thousand rows, and every chart over
        it has a single bar -- which "did it return rows?" cannot see, which
        is why that question is not enough on its own.
        """
        spread = {
            ("customers", "country_code"): 10,
            ("orders", "channel"): 5,
            ("orders", "category"): 6,
            ("service_days", "service"): 6,
        }
        for (table, column), expected in spread.items():
            with self.subTest(column="{}.{}".format(table, column)):
                found = self.connection.execute("SELECT count(DISTINCT {}) FROM {}".format(column, table)).fetchone()[
                    0
                ]
                self.assertEqual(expected, found)

    def test_the_grouped_queries_have_something_to_draw(self):
        # The charts that group: a bar each, not one bar.
        least = {
            "Revenue by category": 6,
            "Revenue by country": 10,
            "Region scorecard": 8,
            "Revenue by region and channel": 20,
            "Channel to category to region": 20,
        }
        by_name = {name: sql for name, _, sql in content.QUERIES}
        for name, expected in least.items():
            with self.subTest(query=name):
                rows = self.connection.execute(by_name[name]).fetchall()
                self.assertGreaterEqual(len(rows), expected, "{} draws {} rows".format(name, len(rows)))

    def test_the_notebook_sql_runs_too(self):
        # Only the cells that read the data source; the rest read each other.
        for name, _, kind, uses_source, sql in content.NOTEBOOK_CELLS:
            if kind == "sql" and uses_source:
                with self.subTest(cell=name):
                    self.assertTrue(self.connection.execute(sql).fetchall())

    def test_it_is_the_same_data_every_time(self):
        # A seeded generator, so a screenshot taken today matches one taken
        # next week and two installs can be compared.
        first = self.connection.execute("SELECT round(sum(total), 2) FROM orders").fetchone()[0]

        again = demo.build_the_data(os.path.join(self.directory, "again.duckdb"))
        from sqldesk.query_runner import deferred

        other = deferred("duckdb").connect(again, read_only=True)
        try:
            second = other.execute("SELECT round(sum(total), 2) FROM orders").fetchone()[0]
        finally:
            other.close()

        self.assertEqual(first, second)


class TestSeeding(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.root = tempfile.mkdtemp()
        patch = mock.patch("sqldesk.settings.UPLOAD_ROOT", self.root)
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def test_it_makes_the_lot(self):
        made = demo.seed(self.factory.org, self.factory.user)

        self.assertEqual(len(content.QUERIES), len(made["queries"]))
        self.assertEqual(len(content.VISUALIZATIONS), len(made["visualizations"]))
        self.assertEqual(len(content.DASHBOARD_WIDGETS), made["dashboard"].widgets.count())
        self.assertEqual(len(content.NOTEBOOK_CELLS), len(made["notebook"].cells))

    def test_seeding_twice_leaves_one_of_everything(self):
        # The first thing anybody does with a demo is seed it again after
        # breaking it.
        demo.seed(self.factory.org, self.factory.user)
        again = demo.seed(self.factory.org, self.factory.user)

        self.assertEqual(len(content.QUERIES), len(again["queries"]))
        self.assertEqual(
            1,
            models.Dashboard.query.filter(
                models.Dashboard.org == self.factory.org, models.Dashboard.name == content.DASHBOARD
            ).count(),
        )
        self.assertEqual(len(content.DASHBOARD_WIDGETS), again["dashboard"].widgets.count())
        # Counted in the database rather than off the relationship, which
        # still holds the rows that were just deleted.
        self.assertEqual(
            len(content.NOTEBOOK_CELLS),
            models.NotebookCell.query.filter(models.NotebookCell.notebook_id == again["notebook"].id).count(),
        )

    def test_the_widget_with_tabs_gets_them(self):
        made = demo.seed(self.factory.org, self.factory.user)

        tabbed = [w for w in made["dashboard"].widgets.all() if (w.options or {}).get("tabs")]
        self.assertTrue(tabbed, "no widget carries tabs, so the demo does not show them")
        for widget in tabbed:
            self.assertIn(widget.visualization.type, models.Visualization.TABBABLE)

    def test_the_notebook_chains_sql_into_python_and_back(self):
        made = demo.seed(self.factory.org, self.factory.user)
        cells = sorted(made["notebook"].cells, key=lambda c: c.position)

        kinds = [cell.kind for cell in cells]
        self.assertIn("python", kinds)
        self.assertIn("sql", kinds)
        # The first cell is the only one with a data source: everything after
        # it reads the cells above, which is the point being demonstrated.
        self.assertIsNotNone(cells[0].data_source_id)
        self.assertTrue(all(cell.data_source_id is None for cell in cells[1:]))

    def test_remove_takes_away_what_seed_made(self):
        demo.seed(self.factory.org, self.factory.user)

        gone = demo.remove(self.factory.org)

        self.assertEqual(len(content.QUERIES), gone["queries"])
        self.assertEqual(1, gone["dashboards"])
        self.assertEqual(1, gone["notebooks"])
        self.assertEqual(1, gone["data_sources"])

    def test_remove_leaves_somebody_elses_work_alone(self):
        demo.seed(self.factory.org, self.factory.user)
        mine = self.factory.create_dashboard(name=content.DASHBOARD + " (my copy)")
        my_query = self.factory.create_query(name="Revenue by day")
        db.session.commit()

        demo.remove(self.factory.org)

        self.assertIsNotNone(models.Dashboard.query.get(mine.id))
        self.assertIsNotNone(models.Query.query.get(my_query.id))


class TestTheBoardIsLaidOutOnTheRealGrid(TestCase):
    """
    The first version of this laid widgets out as if the board were six
    columns wide. It is twenty-four, so every widget came out an eighth of
    the page with its chart squashed into the corner -- and nothing failed,
    because a position is just four numbers and any four are valid.

    Both numbers are read from the client here rather than trusted.
    """

    CLIENT = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "client",
        "app",
        "config",
        "dashboard-grid-options.js",
    )

    def grid_columns(self):
        with open(self.CLIENT, encoding="utf-8") as f:
            return int(re.search(r"columns:\s*(\d+)", f.read()).group(1))

    def test_a_full_width_widget_fills_the_board(self):
        # 24 here and 12 for a half; if the client's grid ever changes, this
        # is what says the demo has to change with it.
        self.assertEqual(24, self.grid_columns())

    def test_every_height_matches_what_the_visualization_asks_for(self):
        """
        Each visualization registers its own `defaultRows`. A demo that gave
        a counter and a table the same height would be a demo of a squashed
        table.
        """
        for entry in os.listdir(VIZ):
            index = os.path.join(VIZ, entry, "index.ts")
            if not os.path.exists(index):
                continue
            with open(index, encoding="utf-8") as f:
                source = f.read()
            type_ = re.search(r'^\s*type:\s*"([A-Z_]+)"', source, re.M)
            rows = re.search(r"defaultRows:\s*(\d+)", source)
            if not type_ or not rows:
                continue
            with self.subTest(visualization=type_.group(1)):
                self.assertEqual(
                    int(rows.group(1)),
                    content.HEIGHTS.get(type_.group(1)),
                    "{} asks for {} rows".format(type_.group(1), rows.group(1)),
                )


class TestTheFixtureTheBrowserTestsRead(TestCase):
    """
    `viz-lib/src/visualizations/__demo-fixture.json` carries each demo
    visualization's options and the columns its query really returns, so a
    jest test can ask every visualization's own `getOptions` whether those
    options mean anything.

    Generated from this file, so it has to be regenerated when the demo
    changes -- and this is what says so, rather than the jest test quietly
    checking a stale copy of last month's demo.
    """

    FIXTURE = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "viz-lib",
        "src",
        "visualizations",
        "__demo-fixture.json",
    )

    def test_it_matches_the_demo_it_was_generated_from(self):
        import json

        with open(self.FIXTURE, encoding="utf-8") as f:
            stored = json.load(f)

        expected = [
            {"type": type_, "name": name, "query": query, "options": options}
            for query, type_, name, options in content.VISUALIZATIONS
        ]
        found = [{k: one[k] for k in ("type", "name", "query", "options")} for one in stored]

        self.assertEqual(
            expected,
            found,
            "the demo has changed since the fixture was generated -- regenerate it, "
            "or the browser-side check is reading an old demo",
        )


class TestTheDataIsRelativeToToday(TestCase):
    def test_the_days_are_counted_back_from_now(self):
        # A demo whose "last 90 days" ended in 2026 is a demo of nothing, so
        # the dates are built from `current_date` rather than written down.
        built = "\n".join(data.statements())

        self.assertIn("current_date", built)
        self.assertNotIn("2026-", built)


class TestRemovingADemoThatWasActuallyUsed(BaseTestCase):
    """
    `demo remove` worked right up until somebody ran the demo notebook.

    `notebook_runs.cell_id` points at a cell and does not cascade, so
    deleting the notebook tried to take its cells with it and Postgres
    refused. Every test seeded and removed without running anything, so the
    one state everybody reaches was the one nothing covered.
    """

    def setUp(self):
        super().setUp()
        self.root = tempfile.mkdtemp()
        patch = mock.patch("sqldesk.settings.UPLOAD_ROOT", self.root)
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def test_a_notebook_that_has_run_can_still_be_removed(self):
        org = self.factory.org
        demo.seed(org, self.factory.user)
        notebook = models.Notebook.query.filter(
            models.Notebook.org == org, models.Notebook.name == content.NOTEBOOK
        ).first()
        self.assertIsNotNone(notebook, "the demo should have seeded a notebook")

        cell = models.NotebookCell.query.filter(models.NotebookCell.notebook_id == notebook.id).first()
        self.assertIsNotNone(cell, "the demo notebook should have cells")

        # What running it leaves behind, which is what used to block removal.
        models.db.session.add(
            models.NotebookRun(
                notebook_id=notebook.id,
                cell_id=cell.id,
                user=self.factory.user,
                state=models.NotebookRun.OK,
            )
        )
        models.db.session.commit()

        gone = demo.remove(org)

        self.assertEqual(1, gone["notebooks"])
        self.assertIsNone(
            models.Notebook.query.filter(models.Notebook.org == org, models.Notebook.name == content.NOTEBOOK).first()
        )
