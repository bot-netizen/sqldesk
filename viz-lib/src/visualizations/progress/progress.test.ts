import getOptions from "./getOptions";
import buildOption, { niceCeil, MAX_BARS } from "./buildOption";

// eslint-disable-next-line @typescript-eslint/no-var-requires
const echarts = require("echarts");

const columns = [
  { name: "region", type: "string" },
  { name: "revenue", type: "float" },
  { name: "target", type: "float" },
];
const rows = [
  { region: "EMEA", revenue: 388, target: 420 },
  { region: "North America", revenue: 642, target: 610 },
  { region: "APAC", revenue: 150, target: 380 },
];
const data = { columns, rows };

function build(options: any, d: any = data) {
  return buildOption(d, getOptions(options, d));
}

function valueSeries(option: any) {
  return option.series.find((s: any) => s.name === "value");
}

describe("Visualizations -> Progress -> options", () => {
  test("defaults: text column for labels, first number for values, no target", () => {
    const o = getOptions({}, data);
    expect(o.labelColumn).toBe("region");
    expect(o.valueColumn).toBe("revenue");
    expect(o.targetColumn).toBe("");
    expect(o.target).toBeNull();
  });

  test("choosing to number the rows sticks", () => {
    expect(getOptions({ labelColumn: "" }, data).labelColumn).toBe("");
  });
});

describe("Visualizations -> Progress -> what it draws", () => {
  test("problems are said, not drawn", () => {
    expect(build({}, { columns, rows: [] }).problem).toMatch(/No rows/);
    expect(build({ valueColumn: "region" }).problem).toMatch(/has no numbers/);
  });

  test("with a target column, each bar is percent of its own target", () => {
    const { option, rows: read } = build({ targetColumn: "target" });
    expect(read.map((r) => Math.round((r.ratio as number) * 100))).toEqual([92, 105, 39]);
    expect(valueSeries(option).data.map((d: any) => Math.round(d.value))).toEqual([92, 105, 39]);
    // The target tick sits at 100% for every row.
    expect(option.series.find((s: any) => s.name === "target").data).toEqual([
      [100, 0],
      [100, 1],
      [100, 2],
    ]);
    expect(option.xAxis.max).toBe(120);
  });

  test("thresholds read percent of target", () => {
    // Defaults: critical below 70%, warning from 70%, good from 100%.
    const { rows: read } = build({ targetColumn: "target" });
    expect(read.map((r) => r.color)).toEqual(["warning", "good", "critical"]);
  });

  test("one constant target applies to every row", () => {
    const { rows: read } = build({ target: 400 });
    expect(read.map((r) => r.target)).toEqual([400, 400, 400]);
  });

  test("without a target the scale is the values', and thresholds read the value", () => {
    const { option, rows: read } = build({ thresholds: { base: "good", steps: [{ value: 500, color: "critical" }] } });
    expect(option.series.find((s: any) => s.name === "target")).toBeUndefined();
    expect(option.xAxis.max).toBe(1000);
    expect(read.map((r) => r.color)).toEqual(["good", "critical", "good"]);
  });

  test("a scale maximum can be set when there is no target", () => {
    expect(build({ max: 700 }).option.xAxis.max).toBe(700);
  });

  test("the bullet draws bands at the threshold steps; the plain bar does not", () => {
    const bullet = build({ targetColumn: "target" }).option.series.filter((s: any) => s.stack === "bands");
    // 0-70, 70-100, 100-120.
    expect(bullet.map((s: any) => s.data[0])).toEqual([70, 30, 20]);
    expect(
      build({ targetColumn: "target", mode: "bar" }).option.series.filter((s: any) => s.stack === "bands")
    ).toEqual([]);
  });

  test("new numbers keep the signature so bars move rather than redraw", () => {
    const a = build({ targetColumn: "target" });
    const b = build({ targetColumn: "target" }, { columns, rows: rows.map((r) => ({ ...r, revenue: r.revenue + 5 })) });
    expect(b.signature).toBe(a.signature);
  });

  test("long results are cut with a note", () => {
    const many = Array.from({ length: MAX_BARS + 5 }, (_, i) => ({ region: `r${i}`, revenue: i + 1, target: 50 }));
    const built = build({ targetColumn: "target" }, { columns, rows: many });
    expect(built.rows).toHaveLength(MAX_BARS);
    expect(built.note).toBe(`Showing the first ${MAX_BARS} of ${MAX_BARS + 5} rows.`);
  });

  test("labels in the tooltip are escaped", () => {
    const { option } = build({}, { columns, rows: [{ region: "<b>x</b>", revenue: 1, target: 2 }] });
    expect(option.tooltip.formatter({ dataIndex: 0 })).toContain("&lt;b&gt;x&lt;/b&gt;");
  });

  test.each(["bullet", "bar"])("the %s style draws", (mode) => {
    const chart = echarts.init(null, null, { renderer: "svg", ssr: true, width: 480, height: 200 });
    try {
      chart.setOption(build({ targetColumn: "target", mode }).option);
      const svg = chart.renderToSVGString();
      expect(svg).toContain("North America");
      expect(svg).toContain("105%");
    } finally {
      chart.dispose();
    }
  });
});

describe("niceCeil", () => {
  test.each([
    [642, 1000],
    [180, 200],
    [21, 25],
    [0.3, 0.5],
    [0, 1],
  ])("%s -> %s", (n, expected) => {
    expect(niceCeil(n)).toBe(expected);
  });
});
