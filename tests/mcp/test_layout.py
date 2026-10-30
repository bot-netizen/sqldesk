"""
How big a widget is on a dashboard an agent built, and where it sits.

Every widget used to be six rows tall whatever it held -- 150 pixels, which
showed three rows of a table and turned a chart into a strip. The browser has
sized widgets by what they hold since the fork; this is the same table, and
the first test here is the one that matters: it reads viz-lib and fails if the
two ever disagree. A mirrored table that drifts silently would be worse than
no table at all.
"""

import os
import re
import unittest

from sqldesk.mcp import layout

VIZ = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "viz-lib",
    "src",
    "visualizations",
)

#: What the browser falls back to when a visualization declares no width --
#: `defaultSizeX` in client/app/config/dashboard-grid-options.js.
GRID_DEFAULT_COLUMNS = 12


def declared_in_viz_lib():
    """`{TYPE: (rows, columns)}`, read out of the TypeScript."""
    found = {}
    for name in sorted(os.listdir(VIZ)):
        path = os.path.join(VIZ, name, "index.ts")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            source = f.read()
        kind = re.search(r'type:\s*"([A-Z_]+)"', source)
        rows = re.search(r"defaultRows:\s*(\d+)", source)
        if not kind or not rows:
            continue
        columns = re.search(r"defaultColumns:\s*(\d+)", source)
        found[kind.group(1)] = (
            int(rows.group(1)),
            int(columns.group(1)) if columns else GRID_DEFAULT_COLUMNS,
        )
    return found


class TestTheTableMatchesTheBrowser(unittest.TestCase):
    def test_every_visualization_is_the_size_the_browser_gives_it(self):
        """
        The test this file exists for. If viz-lib changes a default and this
        does not, an agent's dashboard quietly stops matching one built by
        hand -- which is exactly the complaint that started this.
        """
        self.assertEqual(declared_in_viz_lib(), layout.SIZES)

    def test_the_sizes_were_actually_read(self):
        """A regex that matched nothing would make the test above vacuous."""
        declared = declared_in_viz_lib()

        self.assertGreater(len(declared), 15)
        self.assertIn("CHART", declared)
        self.assertIn("TABLE", declared)


class TestWhatEachKindGets(unittest.TestCase):
    def test_a_table_is_taller_than_a_chart_and_a_chart_than_a_stat(self):
        self.assertGreater(layout.size_of("TABLE")[0], layout.size_of("CHART")[0])
        self.assertGreater(layout.size_of("CHART")[0], layout.size_of("COUNTER")[0])

    def test_nothing_is_the_old_strip(self):
        """Six rows is 150 pixels. Only a stat is meant to be that small."""
        for kind, (rows, _) in layout.SIZES.items():
            if kind not in ("COUNTER", "DETAILS"):
                self.assertGreaterEqual(rows, 10, "{} is back to being a strip".format(kind))

    def test_a_type_nobody_has_heard_of_gets_a_chart_sized_tile(self):
        self.assertEqual(layout.FALLBACK, layout.size_of("SOMETHING_NEW"))
        self.assertEqual(layout.FALLBACK, layout.size_of(None))

    def test_the_type_is_matched_whatever_its_case(self):
        self.assertEqual(layout.size_of("CHART"), layout.size_of("chart"))


class TestWhereTheyGo(unittest.TestCase):
    def test_three_stats_fit_across_the_top(self):
        places = layout.positions(["COUNTER", "COUNTER", "COUNTER"])

        self.assertEqual([0, 8, 16], [one["col"] for one in places])
        self.assertEqual([0, 0, 0], [one["row"] for one in places])

    def test_a_fourth_stat_starts_a_new_row_under_them(self):
        places = layout.positions(["COUNTER"] * 4)

        self.assertEqual(0, places[3]["col"])
        self.assertEqual(6, places[3]["row"], "it did not drop below the row it could not fit in")

    def test_a_row_drops_by_its_tallest_rather_than_by_the_last_one(self):
        """
        A chart beside a stat: the next row has to clear the chart, or the
        dashboard overlaps itself.
        """
        places = layout.positions(["CHART", "COUNTER", "CHART"])

        self.assertEqual(16, places[2]["row"])

    def test_nothing_overlaps_anything(self):
        """
        The property that actually matters. Checked as rectangles rather than
        by inspecting the algorithm, so it holds however the packing changes.
        """
        kinds = ["COUNTER", "CHART", "TABLE", "COUNTER", "GAUGE", "PIVOT", "COUNTER", "CHART"]
        places = layout.positions(kinds)

        for i, a in enumerate(places):
            for b in places[i + 1 :]:
                apart = (
                    a["col"] + a["sizeX"] <= b["col"]
                    or b["col"] + b["sizeX"] <= a["col"]
                    or a["row"] + a["sizeY"] <= b["row"]
                    or b["row"] + b["sizeY"] <= a["row"]
                )
                self.assertTrue(apart, "{} overlaps {}".format(a, b))

    def test_nothing_hangs_off_the_right_of_the_grid(self):
        places = layout.positions(["TABLE", "COUNTER", "GAUGE", "STATE_TIMELINE", "CHART"])

        for one in places:
            self.assertLessEqual(one["col"] + one["sizeX"], layout.COLUMNS, one)

    def test_a_full_width_widget_gets_a_row_to_itself(self):
        places = layout.positions(["COUNTER", "STATE_TIMELINE", "COUNTER"])

        self.assertEqual(24, places[1]["sizeX"])
        self.assertEqual(0, places[1]["col"])
        self.assertGreater(places[2]["row"], places[1]["row"])

    def test_no_widgets_is_no_positions(self):
        self.assertEqual([], layout.positions([]))
