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

function build(options: any, d: any = data, size = { width: 320, height: 240 }) {
  return buildOption(d, getOptions(options, d), size);
}

function render(option: any, size = { width: 320, height: 240 }) {
  const chart = echarts.init(null, null, { renderer: "svg", ssr: true, width: size.width, height: size.height });
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

describe("Visualizations -> Gauge -> tick labels", () => {
  test("a wide scale ticks in whole numbers while the reading keeps its decimals", () => {
    const { option } = build({ valueColumn: "p95", min: 0, max: 1000, valueFormat: { style: "number", decimals: 1 } });
    const needle = option.series[0];
    expect(needle.axisLabel.formatter(200)).toBe("200");
    expect(needle.detail.formatter(needle.data[0].value)).toBe("212.0");
  });

  test.each([
    [1000, 650],
    [700, 200],
    [320, 240],
    [220, 160],
  ])("the half arc's end labels sit just under the ends of the arc at %ix%i", (w, h) => {
    // Read back out of the rendered SVG, not worked out on paper. Three
    // earlier attempts at placing these passed their own arithmetic while the
    // labels were still on the band, because a gauge's axis label sits on the
    // axis and ignores align, verticalAlign and padding alike.
    const built = build({ valueColumn: "p95", style: "half", min: 0, max: 1000 }, data, { width: w, height: h });
    const svg = render(built.option, { width: w, height: h });

    // `M{leftOuter} {cy}A{outer} ... L{rightInner} {cy}A{inner} ...`
    const arc = /M([\d.]+) ([\d.]+)A([\d.]+) [\d.]+ 0 1 1 [\d.]+ [\d.]+L([\d.]+) [\d.]+A([\d.]+)/.exec(svg);
    expect(arc).not.toBeNull();
    const [leftOuterX, cy, outerR, innerR] = [Number(arc![1]), Number(arc![2]), Number(arc![3]), Number(arc![5])];
    const cx = leftOuterX + outerR;

    const labels = [...svg.matchAll(/<text([^>]*)>([^<]*)</g)]
      .map((m) => ({ attrs: m[1], text: m[2] }))
      .filter((t) => t.text === "0" || t.text === "1,000")
      .map(({ attrs, text }) => {
        const x = Number(/x="([-\d.]+)"/.exec(attrs)![1]);
        const y = Number(/y="([-\d.]+)"/.exec(attrs)![1]);
        const size = Number(/font-size:([\d.]+)px/.exec(attrs)![1]);
        const anchor = /text-anchor="(\w+)"/.exec(attrs)![1];
        const width = text.length * size * 0.6;
        const left = anchor === "end" ? x - width : anchor === "start" ? x : x - width / 2;
        return { text, x, top: y - size / 2, left, right: left + width };
      });
    expect(labels).toHaveLength(2);

    labels.forEach(({ x, top, left, right }) => {
      // Below the arc, which is what keeps it off both the band and the
      // reading inside it -- and close enough to read as belonging to it.
      expect(top).toBeGreaterThanOrEqual(cy);
      expect(top - cy).toBeLessThanOrEqual(12);
      // Anchored under the end of the arc, between the band's two edges.
      const fromCentre = Math.abs(cx - x);
      expect(fromCentre).toBeGreaterThanOrEqual(innerR);
      expect(fromCentre).toBeLessThanOrEqual(outerR);
      // And still on the widget.
      expect(left).toBeGreaterThanOrEqual(0);
      expect(right).toBeLessThanOrEqual(w);
    });
  });

  test("only the two ends are labelled", () => {
    const { option } = build({ valueColumn: "p95", style: "half", min: 0, max: 1000 });
    // The arc itself draws no labels; a second, invisible axis sitting a
    // little lower draws the two ends.
    expect(option.series[0].axisLabel.show).toBe(false);
    const format = option.series[1].axisLabel.formatter;
    expect(format(0)).toBe("0");
    expect(format(1000)).toBe("1,000");
    expect(format(500)).toBe("");
  });

  test("a narrow scale keeps the decimals it needs", () => {
    const share = { columns: [{ name: "share", type: "float" }], rows: [{ share: 0.42 }] };
    const { option } = build(
      { valueColumn: "share", min: 0, max: 1, valueFormat: { style: "number", decimals: 1 } },
      share
    );
    expect(option.series[0].axisLabel.formatter(0.2)).toBe("0.2");
  });

  describe("every part of a gauge sits on the same arc", () => {
    // The arc used to be written out four times -- dial, end labels, the
    // marker's angles, the marker's radius again as a number -- so a target
    // marker could end up on a circle the dial was not drawn on.
    test.each(["needle", "half", "ring"])("%s", (style) => {
      const { option } = build({ valueColumn: "p95", style, target: 400, min: 0, max: 1000 });
      const dial = option.series[0];
      const marker = option.series[option.series.length - 1];

      expect(option.series.length).toBeGreaterThan(1);
      expect(marker.startAngle).toBe(dial.startAngle);
      expect(marker.endAngle).toBe(dial.endAngle);
      expect(marker.radius).toBe(dial.radius);
      expect(marker.center).toEqual(dial.center);
    });

    test("except the half style's end labels, which are deliberately lower", () => {
      const { option } = build({ valueColumn: "p95", style: "half", min: 0, max: 1000 });
      const [dial, labels] = option.series;

      expect(labels.radius).toBe(dial.radius);
      expect(labels.startAngle).toBe(dial.startAngle);
      // Pixels, a few below the arc's own centre, which is 72% of 240.
      expect(labels.center[1]).toBeGreaterThan(0.72 * 240);
    });
  });
});
