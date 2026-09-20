import getOptions from "./getOptions";
import buildOption from "./buildOption";

// eslint-disable-next-line @typescript-eslint/no-var-requires
const echarts = require("echarts");

/*
  The bars are drawn by `renderItem` rather than by a bar series, so nothing
  but this checks where they actually land. The arithmetic behind them is
  covered in bars.test.ts; what is measured here is the drawing:

  - each bar starts exactly where the last one ended, which is the whole point
    of a waterfall and the thing an off-by-one in the coordinate maths breaks
    while still producing a plausible-looking chart,
  - a fall is drawn downwards from the previous level, not upwards from zero,
  - a total stands on the baseline, and
  - the baseline is on the chart at all.
*/

const columns = [
  { name: "step", type: "string" },
  { name: "amount", type: "float" },
  { name: "subtotal", type: "boolean" },
];

const SIZE = { width: 600, height: 400 };

function build(rows: any[], overrides: any = {}) {
  const data = { columns, rows };
  return buildOption(data, getOptions({ labelColumn: "step", valueColumn: "amount", ...overrides }, data));
}

interface Box {
  left: number;
  right: number;
  top: number;
  bottom: number;
  fill: string;
}

/** Every rectangle the bar series drew, in the order it drew them. */
function bars(built: any): Box[] {
  // containLabel measures text, and jsdom has no canvas to measure it with.
  // The bars do not depend on it, so it is off for the measurement.
  const option = { ...built.option, grid: { ...built.option.grid, containLabel: false } };
  const chart = echarts.init(null, null, { renderer: "svg", ssr: true, ...SIZE });
  let svg: string;
  try {
    chart.setOption(option);
    svg = chart.renderToSVGString();
  } finally {
    chart.dispose();
  }

  // The bar series is the last one, so it carries the highest series index.
  const seriesIndex = option.series.length - 1;
  const paths = svg.match(new RegExp(`<path [^>]*ecmeta_series_index="${seriesIndex}"[^>]*>`, "g")) || [];
  return paths.map((path) => {
    const d = (path.match(/ d="([^"]+)"/) as RegExpMatchArray)[1];
    // Only the straight segments: the rounded corners are arcs, whose radius
    // and flag arguments would be read as coordinates otherwise.
    const points = [...d.matchAll(/[ML](-?[\d.]+) (-?[\d.]+)/g)].map((m) => [Number(m[1]), Number(m[2])]);
    const xs = points.map((p) => p[0]);
    const ys = points.map((p) => p[1]);
    return {
      left: Math.min(...xs),
      right: Math.max(...xs),
      top: Math.min(...ys),
      bottom: Math.max(...ys),
      fill: ((path.match(/ fill="(#[0-9a-fA-F]{6})"/) as RegExpMatchArray) || [])[1],
    };
  });
}

describe("the waterfall, as drawn", () => {
  const rising = [
    { step: "Open", amount: 100 },
    { step: "Sales", amount: 40 },
    { step: "Refunds", amount: -60 },
  ];

  test("each bar starts exactly where the last one ended", () => {
    const drawn = bars(build(rising, { showTotal: false }));
    expect(drawn).toHaveLength(3);
    // Bar 0 rises from the baseline to 100, so bar 1 starts at bar 0's top.
    expect(drawn[1].bottom).toBeCloseTo(drawn[0].top, 1);
    // Bar 2 falls from 140, which is bar 1's top.
    expect(drawn[2].top).toBeCloseTo(drawn[1].top, 1);
  });

  test("a fall goes down from the last level, not up from zero", () => {
    const drawn = bars(build(rising, { showTotal: false }));
    const fall = drawn[2];
    const baseline = drawn[0].bottom;
    // 140 down to 80: it ends above the baseline, having started below the top.
    expect(fall.bottom).toBeLessThan(baseline);
    expect(fall.top).toBeGreaterThan(0);
    expect(fall.bottom).toBeGreaterThan(fall.top);
  });

  test("rises, falls and totals are told apart by colour", () => {
    const drawn = bars(build(rising, { showTotal: true }));
    expect(drawn[0].fill).toBe(drawn[1].fill);
    expect(drawn[2].fill).not.toBe(drawn[0].fill);
    expect(drawn[3].fill).not.toBe(drawn[0].fill);
    expect(drawn[3].fill).not.toBe(drawn[2].fill);
  });

  test("the total stands on the baseline", () => {
    const built = build(rising, { showTotal: true });
    const drawn = bars(built);
    expect(drawn[3].bottom).toBeCloseTo(drawn[0].bottom, 1);
  });

  test("a subtotal part way through stands on the baseline too, and does not move the running total", () => {
    const drawn = bars(
      build(
        [
          { step: "Revenue", amount: 100, subtotal: false },
          { step: "Costs", amount: -40, subtotal: false },
          { step: "Gross", amount: 0, subtotal: true },
          { step: "Tax", amount: -10, subtotal: false },
        ],
        { totalColumn: "subtotal", showTotal: false }
      )
    );
    const baseline = drawn[0].bottom;
    expect(drawn[2].bottom).toBeCloseTo(baseline, 1);
    // Tax carries on from 60, where Costs left off -- not from 120.
    expect(drawn[3].top).toBeCloseTo(drawn[1].bottom, 1);
  });

  test("bars sit in the order the rows came in, left to right", () => {
    const drawn = bars(build(rising, { showTotal: true }));
    drawn.slice(1).forEach((bar, i) => expect(bar.left).toBeGreaterThan(drawn[i].left));
  });

  test("the bars do not touch, so each step reads separately", () => {
    const drawn = bars(build(rising, { showTotal: true }));
    drawn.slice(1).forEach((bar, i) => expect(bar.left).toBeGreaterThan(drawn[i].right));
  });

  test("there is room above the tallest bar for its label", () => {
    const built = build(rising, { showTotal: true, showValues: true });
    const top = Math.min(...bars(built).map((b) => b.top));
    expect(top).toBeGreaterThan(built.option.grid.top);
  });

  test("a step that changes nothing is still visible", () => {
    // A zero-height rectangle is no rectangle, and the step would look missing.
    const drawn = bars(
      build(
        [
          { step: "a", amount: 50 },
          { step: "flat", amount: 0 },
        ],
        { showTotal: false }
      )
    );
    expect(drawn[1].bottom - drawn[1].top).toBeGreaterThan(0);
  });

  test("a running total that crosses zero still draws against the baseline", () => {
    // The stacked-bar trick fails here, because ECharts stacks positive and
    // negative values separately; drawing the rectangles outright does not.
    const built = build(
      [
        { step: "a", amount: 40 },
        { step: "b", amount: -100 },
        { step: "c", amount: 20 },
      ],
      { showTotal: true }
    );
    const drawn = bars(built);
    const baseline = drawn[0].bottom;
    // b starts at 40 (above the baseline) and ends at -60 (below it).
    expect(drawn[1].top).toBeLessThan(baseline);
    expect(drawn[1].bottom).toBeGreaterThan(baseline);
    // And the total, at -40, hangs below the baseline.
    expect(drawn[3].top).toBeCloseTo(baseline, 1);
    expect(drawn[3].bottom).toBeGreaterThan(baseline);
  });

  test("the steps between bars are drawn at the level they join", () => {
    const built = build(rising, { showTotal: false, showConnectors: true });
    const drawn = bars(built);
    const option = { ...built.option, grid: { ...built.option.grid, containLabel: false } };
    const chart = echarts.init(null, null, { renderer: "svg", ssr: true, ...SIZE });
    chart.setOption(option);
    const svg = chart.renderToSVGString();
    chart.dispose();

    const connectors = (svg.match(/<path [^>]*stroke-dasharray[^>]*>/g) || []).map((path: string) => {
      const d = (path.match(/ d="M([\d.]+) ([\d.]+)L([\d.]+) ([\d.]+)"/) as RegExpMatchArray).slice(1).map(Number);
      return { x1: d[0], y1: d[1], x2: d[2], y2: d[3] };
    });
    expect(connectors).toHaveLength(2);
    // Level, and spanning the gap between the bars they join.
    connectors.forEach((c: { y1: number; y2: number }) => expect(c.y1).toBeCloseTo(c.y2, 5));
    expect(connectors[0].y1).toBeCloseTo(drawn[0].top, 1);
    expect(connectors[0].x1).toBeCloseTo(drawn[0].right, 1);
    expect(connectors[0].x2).toBeCloseTo(drawn[1].left, 1);
  });

  test("no steps when they are turned off", () => {
    const built = build(rising, { showConnectors: false });
    expect(built.option.series.map((s: any) => s.id)).toEqual(["bars"]);
  });
});

describe("the waterfall's chart options", () => {
  test("says what it adds up to, for a screen reader", () => {
    const built = build(
      [
        { step: "a", amount: 10 },
        { step: "b", amount: 5 },
      ],
      { showTotal: true }
    );
    expect(built.option.aria.label.description).toContain("ending at 15");
  });

  test("the baseline is always on the chart", () => {
    const allPositive = build([{ step: "a", amount: 10 }]);
    expect(allPositive.option.yAxis.min).toBe(0);
    const allNegative = build([{ step: "a", amount: -10 }]);
    expect(allNegative.option.yAxis.min).toBe(-10);
  });

  test("the tooltip shows a change and the level it moves between", () => {
    const built = build(
      [
        { step: "a", amount: 10 },
        { step: "b", amount: -4 },
      ],
      { showTotal: true }
    );
    const tooltip = (index: number) => built.option.tooltip.formatter({ dataIndex: index });
    expect(tooltip(0)).toContain("+10");
    expect(tooltip(1)).toContain("10 → 6");
    // A total is a level, not a change, so no sign on it.
    expect(tooltip(2)).not.toContain("→");
  });

  describe("when there is nothing to draw", () => {
    test("no rows", () => {
      expect(build([]).problem).toBe("No rows to show.");
    });

    test("a column that is not in the result", () => {
      expect(build([{ step: "a", amount: 1 }], { valueColumn: "gone" }).problem).toBe(
        "Choose a value column in the editor."
      );
    });

    test("a column with no numbers in it", () => {
      const built = build([
        { step: "a", amount: null },
        { step: "b", amount: "n/a" },
      ]);
      expect(built.problem).toBe("“amount” holds no numbers to add up.");
    });
  });

  test("new levels for the same steps can tween; different steps redraw", () => {
    const same = build([
      { step: "a", amount: 10 },
      { step: "b", amount: 5 },
    ]).signature;
    const alsoSame = build([
      { step: "a", amount: 12 },
      { step: "b", amount: 7 },
    ]).signature;
    const different = build([
      { step: "a", amount: 10 },
      { step: "c", amount: 5 },
    ]).signature;
    expect(alsoSame).toBe(same);
    expect(different).not.toBe(same);
  });

  test("a step turning from a rise into a fall redraws rather than tweening colour", () => {
    const up = build([{ step: "a", amount: 10 }]).signature;
    const down = build([{ step: "a", amount: -10 }]).signature;
    expect(down).not.toBe(up);
  });
});
