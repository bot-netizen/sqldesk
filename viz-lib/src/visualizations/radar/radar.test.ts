import getOptions from "./getOptions";
import buildOption from "./buildOption";
import { webLayout } from "./buildOption";
import buildSpokes from "./spokes";

/*
  The scaling is the argument of a radar chart. Several measures share one web
  only because each spoke states where it ends, and a spoke that ends in the
  wrong place turns a weak reading into a strong-looking shape with nothing on
  screen to say so.
*/

const columns = [
  { name: "team", type: "string" },
  { name: "revenue", type: "float" },
  { name: "orders", type: "integer" },
  { name: "satisfaction", type: "float" },
];

const rows = [
  { team: "North", revenue: 90000, orders: 420, satisfaction: 4.1 },
  { team: "South", revenue: 120000, orders: 260, satisfaction: 4.6 },
];

function build(overrides: any = {}, data: any = { columns, rows }) {
  return buildOption(data, getOptions({ labelColumn: "team", ...overrides }, data));
}

describe("buildSpokes", () => {
  const measures = ["revenue", "orders", "satisfaction"];

  test("per-spoke gives each measure its own scale", () => {
    const spokes = buildSpokes(rows, measures, "per-spoke");
    // Satisfaction out of 5 and revenue out of 120,000 cannot share a scale
    // and still say anything.
    expect(spokes[0].max).toBeGreaterThan(100000);
    expect(spokes[2].max).toBeLessThan(10);
  });

  test("each spoke reaches past its largest value, so the point is not on the rim", () => {
    const spokes = buildSpokes(rows, measures, "per-spoke");
    expect(spokes[0].max).toBeGreaterThan(120000);
    expect(spokes[1].max).toBeGreaterThan(420);
  });

  test("shared puts every spoke on one scale", () => {
    const spokes = buildSpokes(rows, measures, "shared");
    expect(new Set(spokes.map((s) => s.max)).size).toBe(1);
    expect(spokes[0].max).toBeGreaterThan(120000);
  });

  test("spokes keep the order they were asked for", () => {
    expect(buildSpokes(rows, measures, "per-spoke").map((s) => s.name)).toEqual(measures);
    expect(buildSpokes(rows, [...measures].reverse(), "per-spoke").map((s) => s.name)).toEqual([...measures].reverse());
  });

  test("a negative value opens the scale below zero rather than clipping", () => {
    const withLoss = [{ a: -40 }, { a: 100 }];
    expect(buildSpokes(withLoss, ["a"], "per-spoke")[0].min).toBe(-40);
  });

  test("a spoke with no numbers still has a length", () => {
    // Zero-length spokes make ECharts divide by zero and draw nothing at all.
    const spokes = buildSpokes([{ a: "n/a" }], ["a"], "per-spoke");
    expect(spokes[0].max).toBeGreaterThan(0);
  });

  test("a column of zeroes still has a length", () => {
    expect(buildSpokes([{ a: 0 }, { a: 0 }], ["a"], "per-spoke")[0].max).toBeGreaterThan(0);
  });
});

describe("webLayout", () => {
  test("the legend gets room of its own, so a spoke name does not land on it", () => {
    // ECharts sizes a radar against the whole canvas and knows nothing about
    // the legend underneath, which is exactly how the bottom spoke's name
    // ended up written across it.
    const withLegend = webLayout({ width: 700, height: 190 }, true);
    const without = webLayout({ width: 700, height: 190 }, false);
    expect(withLegend.centreY).toBeLessThan(without.centreY);
    expect(withLegend.radius).toBeLessThan(without.radius);
    // The web plus a spoke name stays clear of where the legend sits.
    expect(withLegend.centreY + withLegend.radius).toBeLessThan(190 - 20);
  });

  test("the web grows with the widget", () => {
    expect(webLayout({ width: 700, height: 600 }, true).radius).toBeGreaterThan(
      webLayout({ width: 700, height: 190 }, true).radius
    );
  });

  test("a widget too small for a web still gets one", () => {
    // Zero or negative radius makes ECharts draw nothing at all.
    expect(webLayout({ width: 40, height: 30 }, true).radius).toBeGreaterThan(0);
  });

  test("room is left outside the web for the spoke names", () => {
    const square = webLayout({ width: 400, height: 400 }, false);
    expect(square.radius).toBeLessThan(200);
  });
});

describe("the radar", () => {
  test("one shape per row, named from the name column", () => {
    const built = build();
    expect(built.option.series[0].data.map((d: any) => d.name)).toEqual(["North", "South"]);
  });

  test("each shape carries one reading per spoke, in the spokes' order", () => {
    const built = build({ valueColumns: ["orders", "revenue", "satisfaction"] });
    expect(built.option.series[0].data[0].value).toEqual([420, 90000, 4.1]);
  });

  test("a gap stays a gap rather than being read as zero", () => {
    // Zero is a reading; a missing value is not, and drawing it as zero would
    // make an absent measure look like a terrible one.
    const built = build({}, { columns, rows: [{ team: "X", revenue: 10, orders: null, satisfaction: 3 }] });
    expect(built.option.series[0].data[0].value).toEqual([10, null, 3]);
  });

  test("rows are numbered when there is no name column", () => {
    const built = build({ labelColumn: "" });
    expect(built.option.series[0].data.map((d: any) => d.name)).toEqual(["Row 1", "Row 2"]);
  });

  test("too many rows are cut off, and it says so", () => {
    const many = Array.from({ length: 30 }, (_, i) => ({ team: `T${i}`, revenue: i, orders: i, satisfaction: i }));
    const built = build({}, { columns, rows: many });
    expect(built.option.series[0].data).toHaveLength(12);
    expect(built.note).toContain("first 12 of 30");
  });

  test("filling the shapes is optional", () => {
    expect(build({ showArea: true }).option.series[0].data[0].areaStyle).toBeDefined();
    expect(build({ showArea: false }).option.series[0].data[0].areaStyle).toBeUndefined();
  });

  describe("when there is nothing to draw", () => {
    test("no rows", () => {
      expect(build({}, { columns, rows: [] }).problem).toBe("No rows to show.");
    });

    test("fewer than three measures", () => {
      // Two spokes is a line, not a web.
      expect(build({ valueColumns: ["revenue", "orders"] }).problem).toContain("at least 3 measures");
    });

    test("measures that are not in the result", () => {
      expect(build({ valueColumns: ["gone", "also_gone", "missing"] }).problem).toContain("at least 3 measures");
    });
  });

  test("new readings for the same spokes can tween; new spokes redraw", () => {
    const same = build().signature;
    const different = build({ valueColumns: ["revenue", "orders", "satisfaction", "team"] }).signature;
    expect(different).not.toBe(same);
  });

  test("describes itself for a screen reader", () => {
    const description = build().option.aria.label.description;
    expect(description).toContain("3 measures");
    expect(description).toContain("revenue, orders, satisfaction");
  });
});

describe("the radar's options", () => {
  test("a new radar takes every numeric column as a spoke", () => {
    expect(getOptions({}, { columns, rows }).valueColumns).toEqual(["revenue", "orders", "satisfaction"]);
  });

  test("a saved radar keeps its own spokes, in its own order", () => {
    const saved = { valueColumns: ["satisfaction", "revenue"], labelColumn: "team", scaleMode: "shared" };
    expect(getOptions(saved, { columns, rows })).toMatchObject(saved);
  });
});
