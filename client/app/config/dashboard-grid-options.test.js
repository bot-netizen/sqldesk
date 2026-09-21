import fs from "fs";
import path from "path";
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

/*
  The dotted guides drawn behind the widgets while editing are a CSS
  background, so they cannot read this config directly -- and for the whole of
  the twelve-to-twenty-four change they did not. The grid snapped to
  twenty-four columns and 25px rows while the drawing behind it went on
  showing twelve and 50, which is what someone editing a dashboard actually
  sees and believes.

  DashboardGrid now hands the numbers over as custom properties. These pin
  that arrangement at the source, because nothing else can: the guides are
  decoration, so being wrong costs no test and no error.
*/
describe("the editing guides", () => {
  const less = fs.readFileSync(path.join(__dirname, "../components/dashboards/dashboard-grid.less"), "utf8");
  const component = fs.readFileSync(path.join(__dirname, "../components/dashboards/DashboardGrid.jsx"), "utf8");
  const block = (less.match(/&\.editing-mode\s*\{[\s\S]*?\n {2}\}/) || [""])[0];
  // Comments explain the numbers that used to be here, so they would match
  // the very patterns this is checking for.
  const editing = block.replace(/\/\/[^\n]*/g, "").replace(/\/\*[\s\S]*?\*\//g, "");

  test("the guides are drawn from the grid config, not from numbers of their own", () => {
    expect(editing).toContain("var(--dashboard-grid-columns");
    expect(editing).toContain("var(--dashboard-grid-row-pitch");
    expect(editing).toContain("var(--dashboard-grid-margin");
    // The literals that were there before, and that went stale.
    expect(editing).not.toMatch(/\/\s*12\b/);
    expect(editing).not.toMatch(/\b50px\b/);
  });

  test("the component supplies every property the guides ask for", () => {
    const asked = [...editing.matchAll(/var\((--dashboard-grid-[a-z-]+)/g)].map((m) => m[1]);
    expect(asked.length).toBeGreaterThan(0);
    [...new Set(asked)].forEach((name) => {
      expect(component).toContain(`"${name}"`);
    });
  });

  test("the row guides are dashed as densely as the column guides", () => {
    // Each set of guides is a line with a mask over it that hides most of it.
    // The two masks disagreed -- columns showed 2px of every 5px and rows only
    // 1px -- so the horizontal lines came out half as dark and read as simply
    // missing. Nothing but a person looking at it would notice, so it is
    // pinned here.
    const gaps = [...editing.matchAll(/transparent\s+(\d+)px,\s*#f6f8f9\s+\1px/g)].map((m) => Number(m[1]));
    expect(gaps).toHaveLength(2);
    expect(gaps[0]).toBe(gaps[1]);
  });

  test("each fallback in the stylesheet matches what the config actually says", () => {
    // A fallback that disagrees with the config is the same drift in a
    // quieter form: it is what gets drawn if the property ever goes missing.
    const fallback = (name) => {
      const m = editing.match(new RegExp(`var\\(${name},\\s*([^)]+)\\)`));
      return m ? m[1].trim() : null;
    };
    expect(fallback("--dashboard-grid-columns")).toBe(String(cfg.columns));
    expect(fallback("--dashboard-grid-row-pitch")).toBe(`${cfg.rowHeight}px`);
    expect(fallback("--dashboard-grid-margin")).toBe(`${cfg.margins}px`);
  });
});
