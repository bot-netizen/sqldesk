import moment from "moment";
import getOptions from "../getOptions";
import buildOption from "./buildOption";

const echarts = require("echarts");

/*
  Stacking on a time axis, where a series skips some of the x values.

  Found on the streams picture for the website: orders by region, ten seconds
  to a bar, and a region with no orders in a bucket left every region above it
  floating over a gap or overlapping its neighbour. ECharts stacks by array
  position, so series that do not share their x values stack on the wrong bar.
*/

function series(name: string, points: any[][]) {
  return { name, type: "column", data: points.map(([x, y]) => ({ x, y, $raw: { x, y } })) };
}

const at = (seconds: number) => moment.utc("2026-11-06T22:14:00Z").add(seconds, "seconds");

// south and east have nothing in the middle bucket.
const sparse = [
  series("north", [
    [at(0), 7],
    [at(10), 5],
    [at(20), 4],
  ]),
  series("south", [
    [at(0), 1],
    [at(20), 2],
  ]),
  series("west", [
    [at(0), 11],
    [at(10), 6],
    [at(20), 3],
  ]),
  series("east", [
    [at(0), 8],
    [at(20), 9],
  ]),
];

function stacked(type: string) {
  return buildOption(
    sparse.map((s) => ({ ...s, type })) as any,
    getOptions({
      globalSeriesType: type,
      series: { stacking: "stack" },
      xAxis: { type: "datetime", labels: { enabled: true } },
    })
  );
}

/** Each drawn bar's [bottom, top] in pixels, grouped by its x position. */
function barsByX(built: any) {
  // containLabel measures text, and jsdom has no canvas to measure it with.
  const option = { ...built.option, grid: { ...built.option.grid, containLabel: false }, animation: false };
  const chart = echarts.init(null, null, { renderer: "svg", ssr: true, width: 600, height: 400 });
  const columns = new Map<number, Array<[number, number]>>();
  try {
    chart.setOption(option);
    option.series.forEach((s: any, index: number) => {
      const data = chart.getModel().getSeriesByIndex(index).getData();
      for (let i = 0; i < data.count(); i += 1) {
        const box = data.getItemLayout(i);
        if (!box || !isFinite(box.height) || box.height === 0) {
          continue;
        }
        const x = Math.round(box.x);
        const span: [number, number] = [box.y, box.y + box.height].sort((a, b) => b - a) as [number, number];
        columns.set(x, [...(columns.get(x) || []), span]);
      }
    });
  } finally {
    chart.dispose();
  }
  return columns;
}

describe("Visualizations -> Chart -> ECharts -> stacking on a time axis", () => {
  test("every series is written against the same x values", () => {
    const built = stacked("column");
    const xs = built.option.series.map((s: any) => s.data.map((d: any) => d[0]));
    xs.forEach((list: any[]) => expect(list).toEqual(xs[0]));
    expect(xs[0]).toHaveLength(3);
  });

  test("a missing point is null, not a zero the tooltip would report", () => {
    const south = stacked("column").option.series.find((s: any) => s.name === "south");
    expect(south.data.map((d: any) => d[1])).toEqual([1, null, 2]);
  });

  test("each bar starts where the one below it ends, with no gap and no overlap", () => {
    const columns = barsByX(stacked("column"));
    expect(columns.size).toBe(3);
    columns.forEach((spans) => {
      // Pixels grow downwards: the bottom of the stack has the largest y.
      const ordered = [...spans].sort((a, b) => b[0] - a[0]);
      for (let i = 1; i < ordered.length; i += 1) {
        expect(ordered[i][0]).toBeCloseTo(ordered[i - 1][1], 5);
      }
    });
  });

  test("the middle bar is the two series that have it, stacked", () => {
    const columns = barsByX(stacked("column"));
    const middle = Array.from(columns.keys()).sort((a, b) => a - b)[1];
    expect(columns.get(middle)).toHaveLength(2);
  });

  test("without stacking, series keep only their own points", () => {
    const built = buildOption(
      sparse as any,
      getOptions({ globalSeriesType: "column", xAxis: { type: "datetime", labels: { enabled: true } } })
    );
    const south = built.option.series.find((s: any) => s.name === "south");
    expect(south.data).toHaveLength(2);
  });
});
