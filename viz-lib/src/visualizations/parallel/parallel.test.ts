import getOptions from "./getOptions";
import buildOption, { lineOpacity, linesFrom, problemWith } from "./buildOption";

/*
  Many measures at once, one line per row.

  A scatter compares two things; a chart with six series compares six
  against one axis. Neither answers "which row is unlike the others,
  across everything we measured", which is most of what outlier hunting
  actually is.
*/
const columns = [{ name: "region" }, { name: "revenue" }, { name: "orders" }, { name: "units" }];

function options(overrides: any = {}) {
  return getOptions({ dimensionColumns: ["revenue", "orders", "units"], ...overrides }, {
    columns,
    rows: [],
  } as any);
}

const row = (region: string, revenue: number, orders: number, units: number) => ({
  region,
  revenue,
  orders,
  units,
});

describe("parallel coordinates", () => {
  describe("what it refuses to draw", () => {
    test("no rows", () => {
      expect(problemWith({ rows: [] }, options())).toBeTruthy();
    });

    // One axis is a strip chart. The point is what happens between axes.
    test("fewer than two axes", () => {
      expect(problemWith({ rows: [{}] }, { ...options(), dimensionColumns: ["revenue"] })).toContain("at least two");
    });

    test("and nothing wrong with two", () => {
      expect(problemWith({ rows: [{}] }, { ...options(), dimensionColumns: ["a", "b"] })).toBeNull();
    });

    test("rows that have no numbers in those columns", () => {
      const built = buildOption({ columns, rows: [{ region: "a" }] }, options());

      expect(built.problem).toContain("No row has a number");
      expect(built.option.series).toEqual([]);
    });
  });

  describe("turning rows into lines", () => {
    test("one line per row, values in axis order", () => {
      const { byGroup } = linesFrom([row("a", 10, 2, 5)], options());

      expect(byGroup.get("")).toEqual([[10, 2, 5]]);
    });

    // A line that skips an axis is drawn straight through it, which reads
    // as a value sitting wherever the gap happened to land.
    test("a row missing one measure is dropped, not drawn through the gap", () => {
      const { byGroup, dropped } = linesFrom(
        [row("a", 10, 2, 5), { region: "b", revenue: 1, orders: null, units: 3 }],
        options()
      );

      expect(byGroup.get("")).toEqual([[10, 2, 5]]);
      expect(dropped).toBe(1);
    });

    test("zero is a value, not a gap", () => {
      const { byGroup, dropped } = linesFrom([row("a", 0, 0, 0)], options());

      expect(dropped).toBe(0);
      expect(byGroup.get("")).toEqual([[0, 0, 0]]);
    });

    test("lines are grouped by whatever colours them", () => {
      const { byGroup } = linesFrom(
        [row("north", 1, 1, 1), row("south", 2, 2, 2), row("north", 3, 3, 3)],
        options({ seriesColumn: "region" })
      );

      expect(Array.from(byGroup.keys())).toEqual(["north", "south"]);
      expect(byGroup.get("north")).toHaveLength(2);
    });
  });

  describe("how see-through the lines are", () => {
    // A thousand opaque lines is a solid block with no shape in it; faded
    // too far, a handful of rows disappears altogether.
    test("a handful stay solid", () => {
      expect(lineOpacity(10)).toBeGreaterThan(0.8);
    });

    test("a crowd fades, so overlap becomes density", () => {
      expect(lineOpacity(500)).toBeLessThan(lineOpacity(100));
      expect(lineOpacity(5000)).toBeLessThan(lineOpacity(500));
    });

    test("never to nothing", () => {
      expect(lineOpacity(1000000)).toBeGreaterThan(0);
    });
  });

  describe("the option it builds", () => {
    const data = { columns, rows: [row("a", 10, 2, 5), row("b", 20, 4, 9)] };

    test("one vertical axis per column, named and in order", () => {
      const { option } = buildOption(data, options());

      expect(option.parallelAxis.map((a: any) => a.name)).toEqual(["revenue", "orders", "units"]);
      expect(option.parallelAxis.map((a: any) => a.dim)).toEqual([0, 1, 2]);
    });

    test("one series when nothing colours the lines", () => {
      const { option } = buildOption(data, options());

      expect(option.series).toHaveLength(1);
      expect(option.legend.show).toBe(false);
    });

    test("one series per group when something does", () => {
      const { option } = buildOption(data, options({ seriesColumn: "region" }));

      expect(option.series).toHaveLength(2);
      expect(option.legend.show).toBe(true);
    });

    // On a faded plot this is the only way to follow one row across.
    test("hovering lifts a line clear of the crowd", () => {
      const { option } = buildOption(data, options());

      expect(option.series[0].emphasis.lineStyle.opacity).toBe(1);
      expect(option.series[0].emphasis.lineStyle.width).toBeGreaterThan(option.series[0].lineStyle.width);
    });

    test("changing the axes changes the shape", () => {
      const fewer = options({ dimensionColumns: ["revenue", "orders"] });

      expect(buildOption(data, options()).signature).not.toBe(buildOption(data, fewer).signature);
    });
  });
});
