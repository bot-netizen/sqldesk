import fs from "fs";
import path from "path";
import getOptions from "./getOptions";
import buildOption from "./buildOption";

// eslint-disable-next-line @typescript-eslint/no-var-requires
const echarts = require("echarts");

const columns = [
  { name: "service", type: "string" },
  { name: "p95", type: "float" },
  { name: "limit", type: "integer" },
  { name: "goal", type: "integer" },
];
const rows = [
  { service: "api", p95: 212, limit: 500, goal: 300 },
  { service: "etl", p95: 640, limit: 500, goal: 300 },
];
const data = { columns, rows };

function build(options: any, d: any = data) {
  return buildOption(d, getOptions(options, d), { width: 320, height: 240 });
}

function render(option: any) {
  const chart = echarts.init(null, null, { renderer: "svg", ssr: true, width: 320, height: 240 });
  try {
    chart.setOption(option);
    return chart.renderToSVGString() as string;
  } finally {
    chart.dispose();
  }
}

describe("Visualizations -> Gauge -> options", () => {
  test("picks the first numeric column when none is chosen", () => {
    expect(getOptions({}, data).valueColumn).toBe("p95");
  });

  test("a saved choice survives", () => {
    expect(getOptions({ valueColumn: "limit" }, data).valueColumn).toBe("limit");
  });

  test("an unknown style falls back to the needle", () => {
    expect(getOptions({ style: "3d" }, data).style).toBe("needle");
  });

  test("a cleared target stays cleared", () => {
    expect(getOptions({ target: null }, data).target).toBeNull();
    expect(getOptions({ target: "" }, data).target).toBeNull();
  });
});

describe("Visualizations -> Gauge -> what it draws", () => {
  test("says what is wrong instead of drawing nonsense", () => {
    expect(build({}, { columns, rows: [] }).problem).toMatch(/No rows/);
    expect(build({ valueColumn: "service" }).problem).toMatch(/not a number/);
    expect(build({ valueColumn: "nope" }).problem).toMatch(/Choose a value column/);
    expect(build({ min: 10, max: 10 }).problem).toMatch(/maximum must be above/);
  });

  test("reads the chosen row, counting from the end with negatives", () => {
    expect(build({ rowNumber: 1, max: 1000 }).option.series[0].data[0].value).toBe(212);
    expect(build({ rowNumber: -1, max: 1000 }).option.series[0].data[0].value).toBe(640);
  });

  test("the needle stops at the end of the dial but the number does not", () => {
    // 640 on a 0-500 dial.
    const { option } = build({ rowNumber: -1, max: 500 });
    const series = option.series[0];
    expect(series.data[0].value).toBe(500);
    expect(series.detail.formatter(500)).toBe("640");
    // Mid-tween values are shown as they pass.
    expect(series.detail.formatter(250)).toBe("250");
  });

  test("min and max can come from columns", () => {
    const { option } = build({ maxColumn: "limit", max: 9999 });
    expect(option.series[0].max).toBe(500);
  });

  test("bands follow the thresholds along the arc", () => {
    const { option } = build({
      max: 500,
      thresholds: {
        base: "good",
        steps: [
          { value: 250, color: "warning" },
          { value: 400, color: "critical" },
        ],
      },
    });
    const bands = option.series[0].axisLine.lineStyle.color;
    expect(bands.map((b: any) => b[0])).toEqual([0.5, 0.8, 1]);
    expect(bands.map((b: any) => b[1])).toEqual(["#1e7a4c", "#9a6510", "#b4342c"]);
  });

  test("the ring takes the colour of the band the value is in", () => {
    const { option } = build({
      style: "ring",
      max: 500,
      thresholds: { base: "good", steps: [{ value: 200, color: "warning" }] },
    });
    expect(option.series[0].progress.itemStyle.color).toBe("#9a6510");
  });

  test("a target adds a marker, from a constant or a column", () => {
    expect(build({ max: 500 }).option.series).toHaveLength(1);
    expect(build({ max: 500, target: 350 }).option.series[1].data[0].value).toBe(350);
    expect(build({ max: 500, targetColumn: "goal" }).option.series[1].data[0].value).toBe(300);
  });

  test("a new value keeps the signature, so the needle moves instead of redrawing", () => {
    const before = build({ max: 1000 }, data);
    const after = build({ max: 1000 }, { columns, rows: [{ ...rows[0], p95: 480 }] });
    expect(after.signature).toBe(before.signature);
    expect(after.option.series[0].data[0].value).toBe(480);
  });

  test("changing the dial changes the signature", () => {
    expect(build({ max: 1000 }).signature).not.toBe(build({ max: 900 }).signature);
    expect(build({ style: "ring" }).signature).not.toBe(build({ style: "half" }).signature);
  });

  test("describes itself for screen readers", () => {
    const { option } = build({ max: 500, target: 300, valueFormat: { suffix: " ms" } });
    expect(option.aria.label.description).toBe("p95: 212 ms, on a scale from 0 ms to 500 ms, target 300 ms.");
  });

  test.each(["needle", "ring", "half"])("the %s style draws", (style) => {
    const svg = render(build({ style, max: 500, target: 300 }).option);
    expect(svg).toContain("<svg");
    // The value is drawn as text.
    expect(svg).toContain("212");
  });
});

describe("Visualizations -> Gauge -> registration", () => {
  test("GaugeChart is registered in the tree-shaken barrel", () => {
    const source = fs.readFileSync(path.join(__dirname, "../echarts/index.ts"), "utf8");
    expect(source).toContain("GaugeChart");
  });
});
