"""
How big each widget is on a dashboard an agent built, and where it goes.

Every widget used to be six rows tall and half the grid wide, whatever it
held. Six rows is 150 pixels: a table showed three of its rows, a chart was a
strip, and a dashboard an agent made looked nothing like the same dashboard
made by hand. The browser has sized widgets by what they hold since the fork
-- `defaultRows` and `defaultColumns` on each visualization -- and this is the
same table, so the two agree.

**Mirrored rather than imported, because the real one is TypeScript.** It
cannot be read from Python without a build step, so it is copied here and
`tests/mcp/test_layout.py` parses `viz-lib/src/visualizations/*/index.ts` and
fails if the two ever disagree. A table that silently drifts would be worse
than no table.
"""

#: Rows and columns per visualization type, matching viz-lib.
#:
#: The grid is 24 columns and a row is 25 pixels, so a chart at 16 rows is
#: 400px and half the width -- which is what somebody dragging one onto a
#: dashboard gets today.
SIZES = {
    "BOXPLOT": (16, 12),
    "CALENDAR_HEATMAP": (12, 24),
    "CHART": (16, 12),
    "CHOROPLETH": (16, 12),
    "COHORT": (16, 12),
    "COUNTER": (6, 8),
    "DETAILS": (4, 8),
    "FUNNEL": (20, 12),
    "GAUGE": (12, 4),
    "HISTOGRAM": (16, 12),
    "MAP": (16, 12),
    "PIVOT": (20, 12),
    "PROGRESS": (12, 6),
    "RADAR": (16, 8),
    "SANKEY": (14, 12),
    "STATUS_GRID": (10, 12),
    "STATE_TIMELINE": (12, 24),
    "SUNBURST_SEQUENCE": (14, 12),
    "TABLE": (28, 12),
    "TREEMAP": (16, 12),
    "WATERFALL": (16, 12),
    "WORD_CLOUD": (16, 12),
}

#: For a type this does not know -- a visualization added after this was
#: written. Half the grid and the height of a chart: wrong for some things,
#: never the 150-pixel strip that started this.
FALLBACK = (16, 12)

#: The grid a dashboard is laid out on.
COLUMNS = 24


def size_of(visualization_type):
    """`(rows, columns)` for this kind of visualization."""
    return SIZES.get((visualization_type or "").upper(), FALLBACK)


def positions(visualization_types):
    """
    Where each widget goes, left to right and top to bottom.

    Greedy row packing: widgets go across until the next one will not fit in
    what is left of the row, then the row closes at the height of its tallest
    and the next begins under it. Simple on purpose -- an agent's dashboard is
    a starting point somebody then drags around, and a clever packing that
    produced a pleasing but surprising arrangement would be harder to fix than
    a plain one.

    It cannot overlap and it cannot leave a hole above a widget, which are the
    two ways a layout is actually broken.
    """
    placed = []
    col = 0
    row = 0
    tallest = 0

    for one in visualization_types:
        rows, columns = size_of(one)
        columns = min(columns, COLUMNS)
        if col + columns > COLUMNS:
            # The row is full: drop to the bottom of its tallest widget.
            row += tallest
            col = 0
            tallest = 0
        placed.append({"col": col, "row": row, "sizeX": columns, "sizeY": rows, "autoHeight": False})
        col += columns
        tallest = max(tallest, rows)

    return placed
