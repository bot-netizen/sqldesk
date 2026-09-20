import cfg from "./dashboard-grid-options";

/*
  The grid went from twelve columns and 50px rows to twenty-four and 25px,
  and every stored size doubled with it. That is only safe because a widget
  twice as large on a grid twice as fine comes out the same size on screen.
  These pin that, because it is the kind of arithmetic that looks obvious and
  is easy to break by "tidying" one number without the other.
*/

// What react-grid-layout is handed: DashboardGrid passes
// rowHeight={cfg.rowHeight - cfg.margins} and stacks margins between rows.
function pixelHeight(rows, { rowHeight, margins }) {
  return rows * (rowHeight - margins) + (rows - 1) * margins;
}

const OLD_GRID = { columns: 12, rowHeight: 50, margins: 15 };

describe("dashboard grid", () => {
  test("is twice as fine as it was, in both directions", () => {
    expect(cfg.columns).toBe(OLD_GRID.columns * 2);
    expect(cfg.rowHeight * 2).toBe(OLD_GRID.rowHeight);
    // The gutter sits between widgets, not between columns, so it does not
    // scale -- that is what makes the widths work out.
    expect(cfg.margins).toBe(OLD_GRID.margins);
  });

  test("a widget with twice the rows is the same height on screen", () => {
    [1, 2, 3, 5, 8, 14].forEach((rows) => {
      expect(pixelHeight(rows * 2, cfg)).toBe(pixelHeight(rows, OLD_GRID));
    });
  });

  test("the defaults doubled along with the grid, so a new widget is unchanged", () => {
    expect(cfg.defaultSizeX).toBe(12);
    expect(cfg.defaultSizeY).toBe(6);
    expect(cfg.minSizeX).toBe(4);
    expect(cfg.minSizeY).toBe(4);
    expect(cfg.maxSizeX).toBe(cfg.columns);
  });

  test("half, a third and a quarter of the width are all whole numbers of columns", () => {
    // Twelve could not do thirds and quarters both; this is most of the point.
    [2, 3, 4, 6, 8, 12].forEach((share) => {
      expect(cfg.columns % share).toBe(0);
    });
  });
});
