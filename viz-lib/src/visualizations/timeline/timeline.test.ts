import getOptions from "./getOptions";
import buildOption from "./buildOption";

// eslint-disable-next-line @typescript-eslint/no-var-requires
const echarts = require("echarts");

/*
  The bars are drawn by `renderItem`, so nothing but this knows where they
  actually landed. The time arithmetic behind them is covered in spans.test.ts;
  measured here is the drawing: that a bar spans the time it says it does, that
  it sits on its own track, and that a span running past the edge of the window
  is trimmed rather than drawn over the axis.
*/

const columns = [
  { name: "service", type: "string" },
  { name: "started", type: "datetime" },
  { name: "ended", type: "datetime" },
  { name: "status", type: "string" },
];

const SIZE = { width: 800, height: 300 };

const rows = [
  { service: "api", started: "2024-03-05T10:00:00Z", ended: "2024-03-05T10:30:00Z", status: "ok" },
  { service: "api", started: "2024-03-05T11:00:00Z", ended: "2024-03-05T12:00:00Z", status: "down" },
  { service: "db", started: "2024-03-05T10:00:00Z", ended: "2024-03-05T12:00:00Z", status: "ok" },
];

function build(overrides: any = {}, data: any = { columns, rows }) {
  const options = getOptions(
    { laneColumn: "service", startColumn: "started", endColumn: "ended", stateColumn: "status", ...overrides },
    data
  );
  return buildOption(data, options);
}

interface Box {
  left: number;
  right: number;
  top: number;
  bottom: number;
  fill: string;
}

function bars(built: any): Box[] {
  // containLabel measures text, and jsdom has no canvas to measure it with.
  const option = { ...built.option, grid: { ...built.option.grid, containLabel: false } };
  const chart = echarts.init(null, null, { renderer: "svg", ssr: true, ...SIZE });
  let svg: string;
  try {
    chart.setOption(option);
    svg = chart.renderToSVGString();
  } finally {
    chart.dispose();
  }

  const paths = svg.match(/<path [^>]*ecmeta_series_index="0"[^>]*>/g) || [];
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

describe("the timeline, as drawn", () => {
  test("one bar per span", () => {
    expect(bars(build())).toHaveLength(3);
  });

  test("a bar's width is the time it covers", () => {
    const drawn = bars(build());
    // api's second span is an hour; db's is two, so twice as wide.
    const oneHour = drawn[1].right - drawn[1].left;
    const twoHours = drawn[2].right - drawn[2].left;
    expect(twoHours / oneHour).toBeCloseTo(2, 1);
  });

  test("bars on the same track sit at the same height", () => {
    const drawn = bars(build());
    expect(drawn[0].top).toBeCloseTo(drawn[1].top, 1);
    expect(drawn[0].bottom).toBeCloseTo(drawn[1].bottom, 1);
  });

  test("different tracks sit at different heights, and do not overlap", () => {
    const drawn = bars(build());
    expect(drawn[2].top).toBeGreaterThan(drawn[0].bottom);
  });

  test("tracks read top to bottom in the order the query returned them", () => {
    // api came first, so api is the upper track.
    const drawn = bars(build());
    expect(drawn[0].top).toBeLessThan(drawn[2].top);
  });

  test("a bar begins where its start time falls, not at the axis", () => {
    const drawn = bars(build());
    // api's 11:00 span starts half way across a 10:00-12:00 window.
    const windowLeft = Math.min(...drawn.map((b) => b.left));
    const windowRight = Math.max(...drawn.map((b) => b.right));
    const halfWay = windowLeft + (windowRight - windowLeft) / 2;
    expect(drawn[1].left).toBeCloseTo(halfWay, 0);
  });

  test("states are told apart by colour", () => {
    const drawn = bars(build());
    // "ok" and "down" are both in the default mappings.
    expect(drawn[0].fill).toBe(drawn[2].fill);
    expect(drawn[1].fill).not.toBe(drawn[0].fill);
  });

  test("an unmapped state still gets a colour of its own", () => {
    const odd = [
      { service: "api", started: "2024-03-05T10:00:00Z", ended: "2024-03-05T11:00:00Z", status: "provisioning" },
      { service: "api", started: "2024-03-05T11:00:00Z", ended: "2024-03-05T12:00:00Z", status: "draining" },
    ];
    const drawn = bars(build({}, { columns, rows: odd }));
    expect(drawn[0].fill).not.toBe(drawn[1].fill);
  });

  test("a momentary span is still wide enough to see", () => {
    const instant = [
      { service: "api", started: "2024-03-05T10:00:00Z", ended: "2024-03-05T10:00:00Z", status: "ok" },
      { service: "api", started: "2024-03-05T10:00:00Z", ended: "2024-03-05T14:00:00Z", status: "ok" },
    ];
    const drawn = bars(build({}, { columns, rows: instant }));
    expect(drawn[0].right - drawn[0].left).toBeGreaterThanOrEqual(2);
  });

  test("bars stay inside the plot rather than running over the axis", () => {
    const built = build();
    const drawn = bars(built);
    const coordSysLeft = 8;
    drawn.forEach((bar) => {
      expect(bar.left).toBeGreaterThanOrEqual(coordSysLeft - 1);
      expect(bar.right).toBeLessThanOrEqual(SIZE.width);
    });
  });
});

describe("the timeline's chart options", () => {
  test("the window covers every span", () => {
    const built = build();
    expect(built.option.xAxis.min).toBe(Date.parse("2024-03-05T10:00:00Z"));
    expect(built.option.xAxis.max).toBe(Date.parse("2024-03-05T12:00:00Z"));
  });

  test("one track per distinct value, in first-seen order", () => {
    expect(build().option.yAxis.data).toEqual(["api", "db"]);
  });

  test("a run that has not finished is outlined, so it reads as unfinished", () => {
    const running = [{ service: "api", started: "2024-03-05T10:00:00Z", ended: null, status: "down" }];
    const built = build({}, { columns, rows: running });
    expect(built.option.series[0].data[0].itemStyle.borderWidth).toBe(1);
    expect(built.option.series[0].data[0].itemStyle.borderType).toBe("dashed");
  });

  test("a finished run is not outlined", () => {
    expect(build().option.series[0].data[0].itemStyle.borderWidth).toBe(0);
  });

  test("the tooltip says how long, and whether it is over", () => {
    const built = build();
    const tooltip = (i: number) => built.option.tooltip.formatter({ dataIndex: i });
    expect(tooltip(0)).toContain("30 min");
    expect(tooltip(0)).not.toContain("still going");
    const running = build({}, { columns, rows: [{ service: "api", started: "2024-03-05T10:00:00Z", status: "down" }] });
    expect(running.option.tooltip.formatter({ dataIndex: 0 })).toContain("still going");
  });

  test("a mapped state is named the friendlier way in the tooltip", () => {
    const built = build({ mappings: [{ value: "down", text: "Outage", color: "critical" }] });
    expect(built.option.tooltip.formatter({ dataIndex: 1 })).toContain("Outage");
  });

  test("says what it could not place", () => {
    const built = build({}, { columns, rows: [...rows, { service: "api", started: null }] });
    expect(built.note).toContain("1 row had no readable time");
  });

  describe("when there is nothing to draw", () => {
    test("no rows", () => {
      expect(build({}, { columns, rows: [] }).problem).toBe("No rows to show.");
    });

    test("a start column that is not in the result", () => {
      expect(build({ startColumn: "gone" }).problem).toBe("Choose a start time column in the editor.");
    });

    test("a column with no readable times", () => {
      const built = build({}, { columns, rows: [{ service: "api", started: "never" }] });
      expect(built.problem).toBe("No readable times in “started”.");
    });
  });

  test("new times for the same tracks and states can tween; a new track redraws", () => {
    const same = build().signature;
    const different = build({}, { columns, rows: [...rows, { ...rows[0], service: "cache" }] }).signature;
    expect(different).not.toBe(same);
  });
});
