import getOptions from "./getOptions";
import buildOption from "./buildOption";

// eslint-disable-next-line @typescript-eslint/no-var-requires
const echarts = require("echarts");

/*
  The reading tile. A dial spends a whole widget on one number and says
  nothing about how it got there; this style says the number large, the trail
  it took, and where it sits in its range.
*/

const columns = [
  { name: "at", type: "datetime" },
  { name: "p95", type: "float" },
  { name: "goal", type: "integer" },
];
const rows = [
  { at: "2026-01-01T00:00:00", p95: 180, goal: 300 },
  { at: "2026-01-01T01:00:00", p95: 240, goal: 300 },
  { at: "2026-01-01T02:00:00", p95: 212, goal: 300 },
];
const data = { columns, rows };

function build(options: any, d: any = data, size = { width: 360, height: 240 }) {
  return buildOption(d, getOptions({ style: "reading", ...options }, d), size);
}

function render(option: any, size = { width: 360, height: 240 }) {
  const chart = echarts.init(null, null, { renderer: "svg", ssr: true, width: size.width, height: size.height });
  try {
    chart.setOption(option);
    return chart.renderToSVGString() as string;
  } finally {
    chart.dispose();
  }
}

function seriesOfType(option: any, type: string) {
  return option.series.filter((s: any) => s.type === type);
}

describe("Visualizations -> Gauge -> the reading tile", () => {
  test("a gauge being created opens on it", () => {
    expect(getOptions({}, data).style).toBe("reading");
  });

  test("a gauge saved without one keeps the needle it was drawn with", () => {
    // Anything already stored has options, even if `style` is not among them.
    expect(getOptions({ valueColumn: "p95" }, data).style).toBe("needle");
    expect(getOptions({ style: "half" }, data).style).toBe("half");
  });

  test("the number is the thing: no arc, no needle, no ticks", () => {
    const { option } = build({ valueColumn: "p95" });
    const [text] = seriesOfType(option, "gauge");

    expect(option.series.filter((s: any) => s.type === "gauge")).toHaveLength(1);
    expect(text.axisLine.show).toBe(false);
    expect(text.pointer.show).toBe(false);
    expect(text.axisLabel.show).toBe(false);
    expect(text.detail.valueAnimation).toBe(true);
  });

  test("the number counts to its new value and is coloured by its threshold", () => {
    const { option } = build({
      valueColumn: "p95",
      min: 0,
      max: 500,
      trailColumn: "at",
      thresholds: { base: "good", steps: [{ value: 200, color: "critical" }] },
    });
    const [text] = seriesOfType(option, "gauge");

    // 212 is past the 200 step, so critical -- not the base.
    expect(text.detail.color).not.toBe("");
    expect(text.detail.formatter(212)).toBe("212");
    expect(text.data[0].value).toBe(212);
  });

  test("a reading past the maximum says so rather than being clamped", () => {
    const { option } = build({ valueColumn: "p95", min: 0, max: 100, trailColumn: "at" });
    const [text] = seriesOfType(option, "gauge");

    expect(text.detail.formatter(100)).toBe("212");
    // The bullet is clamped, because a bar cannot run off its track.
    const bar = option.series.find((s: any) => s.type === "bar" && !s.stack);
    expect(bar.data[0]).toBe(100);
  });

  test("the bullet carries the range, the bands and the target", () => {
    const { option } = build({
      valueColumn: "p95",
      min: 0,
      max: 500,
      target: 300,
      thresholds: {
        base: "good",
        steps: [
          { value: 200, color: "warning" },
          { value: 400, color: "critical" },
        ],
      },
    });

    const bands = option.series.filter((s: any) => s.stack === "bands");
    expect(bands).toHaveLength(3);
    // The widths add up to the whole range, so the bar behind is exactly full.
    expect(bands.reduce((sum: number, s: any) => sum + s.data[0], 0)).toBeCloseTo(500);

    const target = seriesOfType(option, "scatter");
    expect(target).toHaveLength(1);
    expect(target[0].data[0][0]).toBe(300);
  });

  test("no target means no tick and no third label", () => {
    const { option } = build({ valueColumn: "p95", min: 0, max: 500 });

    expect(seriesOfType(option, "scatter")).toHaveLength(0);
    expect(option.graphic).toHaveLength(2);
  });

  test("the ends of the range are written under the bar", () => {
    const { option } = build({ valueColumn: "p95", min: 0, max: 500 });

    expect(option.graphic.map((g: any) => g.style.text)).toEqual(["0", "500"]);
  });

  test("a trail is drawn over every row, oldest first", () => {
    const { option } = build({ valueColumn: "p95", min: 0, max: 500, trailColumn: "at" });
    const [line] = seriesOfType(option, "line");

    expect(line.data).toEqual([180, 240, 212]);
  });

  test("with a trail column the reading is the newest point, not row 1", () => {
    const newestFirst = { columns, rows: [...rows].reverse() };
    const { option } = build({ valueColumn: "p95", min: 0, max: 500, trailColumn: "at" }, newestFirst);
    const [text] = seriesOfType(option, "gauge");

    expect(text.data[0].value).toBe(212);
    expect(seriesOfType(option, "line")[0].data).toEqual([180, 240, 212]);
  });

  test("without one, the rows keep the order they came back in", () => {
    const { option } = build({ valueColumn: "p95", min: 0, max: 500, rowNumber: 1 });
    const [text] = seriesOfType(option, "gauge");

    expect(text.data[0].value).toBe(180);
    expect(seriesOfType(option, "line")[0].data).toEqual([180, 240, 212]);
  });

  test("one row is a reading with no trail", () => {
    const one = { columns, rows: [rows[0]] };
    const { option } = build({ valueColumn: "p95" }, one);

    expect(seriesOfType(option, "line")).toHaveLength(0);
  });

  test("a widget too short for a trail leaves it out rather than smearing it", () => {
    const { option } = build({ valueColumn: "p95" }, data, { width: 360, height: 110 });

    expect(seriesOfType(option, "line")).toHaveLength(0);
    // The grid it would have used is still there: an option with fewer grids
    // than the one before it cannot merge into a live chart.
    expect(option.grid).toHaveLength(2);
  });

  test("it says what it is showing, for a screen reader", () => {
    const { option } = build({ valueColumn: "p95", min: 0, max: 500, target: 300, trailColumn: "at" });

    expect(option.aria.label.description).toContain("212");
    expect(option.aria.label.description).toContain("target 300");
    expect(option.aria.label.description).toContain("3 readings");
  });

  test("it draws", () => {
    const { option, problem } = build({ valueColumn: "p95", min: 0, max: 500, target: 300, trailColumn: "at" });
    expect(problem).toBeNull();

    const svg = render(option);
    expect(svg).toContain("212");
    expect(svg).toContain("<path");
  });

  test("its signature changes when the shape does, and not when only the value does", () => {
    const base = build({ valueColumn: "p95", min: 0, max: 500 }).signature;

    expect(
      build({ valueColumn: "p95", min: 0, max: 500 }, { columns, rows: [rows[0], rows[1], rows[0]] }).signature
    ).toBe(base);
    expect(build({ valueColumn: "p95", min: 0, max: 500, target: 300 }).signature).not.toBe(base);
    expect(build({ valueColumn: "p95", min: 0, max: 1000 }).signature).not.toBe(base);
    expect(build({ valueColumn: "p95", min: 0, max: 500 }, { columns, rows: rows.slice(0, 2) }).signature).not.toBe(
      base
    );
  });

  test("a needle gauge is unchanged by any of this", () => {
    const { option } = build({ style: "needle", valueColumn: "p95", min: 0, max: 500 });

    expect(option.series[0].pointer.show).not.toBe(false);
    expect(option.grid).toBeUndefined();
  });
});
