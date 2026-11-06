/**
 * Renders every supported chart type with the real ECharts, headless.
 *
 * The other tests in this directory assert the shape of the option object,
 * which cannot tell you whether ECharts understands it: a series type that does
 * not exist, or a `renderItem` that throws, produces a perfectly reasonable
 * option and an empty canvas.
 *
 * This requires ECharts' CommonJS build rather than our own barrel. The barrel
 * imports `echarts/core`, which is ESM, and babel-jest will not transform it --
 * viz-lib configures babel through `.babelrc`, which babel applies only to
 * files inside the package. The full build behaves identically for everything
 * asserted here; what it cannot check is which series types we registered, so
 * that is asserted separately at the bottom of this file.
 *
 * `ssr: true` means no canvas and no DOM -- the chart renders to an SVG string.
 */
import fs from "fs";
import path from "path";
import buildOption from "./buildOption";
import getOptions from "../getOptions";

// eslint-disable-next-line @typescript-eslint/no-var-requires
const echarts = require("echarts");

function options(overrides: any = {}) {
  return getOptions({ sortX: false, ...overrides });
}

function series(name: string, points: any[][], keys = ["x", "y"]) {
  return {
    name,
    type: "column",
    data: points.map((values) => {
      const point: any = {};
      keys.forEach((key, index) => {
        point[key] = values[index];
      });
      return { ...point, $raw: point };
    }),
  };
}

function render(chartData: any[], chartOptions: any) {
  const built = buildOption(chartData, chartOptions);
  const chart = echarts.init(null, null, { renderer: "svg", ssr: true, width: 600, height: 400 });
  try {
    chart.setOption(built.option);
    return { svg: chart.renderToSVGString() as string, built };
  } finally {
    chart.dispose();
  }
}

/**
 * Marks ECharts actually drew, excluding the legend's own swatches.
 *
 * Counts every shape, not just <path>: a custom series can return a circle or a
 * rect, and counting paths alone silently misses them.
 */
function drawnMarks(svg: string) {
  return svg
    .split(/(?=<(?:path|circle|rect|polyline|polygon|line)\b)/)
    .filter((element) => element.includes('ecmeta_ssr_type="chart"')).length;
}

describe("Visualizations -> Chart -> ECharts -> rendering for real", () => {
  test("a time series is labelled with times, spread across the axis", () => {
    // Left on the editor's automatic axis, a datetime column was drawn on a
    // number line from 0 and labelled in raw milliseconds.
    const moment = require("moment"); // eslint-disable-line global-require
    const start = moment.utc("2026-09-19T20:50:00Z");
    const points = [0, 1, 2, 3, 4, 5].map((i) => [start.clone().add(i, "minutes"), 300 + i * 10]);
    const { svg } = render(
      [{ ...series("rps", points), type: "line" }],
      options({ globalSeriesType: "line", xAxis: { type: "-", labels: { enabled: true } } })
    );

    expect(svg).not.toMatch(/>1789\d{9}</);
    expect(svg).toMatch(/>\d{2}:\d{2}</);
  });

  const cases: [string, any[], any][] = [
    [
      "column",
      [
        series("s", [
          ["a", 1],
          ["b", 2],
        ]),
      ],
      options({ globalSeriesType: "column" }),
    ],
    [
      "line",
      [
        series("s", [
          ["a", 1],
          ["b", 2],
        ]),
      ],
      options({ globalSeriesType: "line" }),
    ],
    [
      "area",
      [
        series("s", [
          ["a", 1],
          ["b", 2],
        ]),
      ],
      options({ globalSeriesType: "area" }),
    ],
    [
      "scatter",
      [
        series("s", [
          ["a", 1],
          ["b", 2],
        ]),
      ],
      options({ globalSeriesType: "scatter" }),
    ],
    [
      "pie",
      [
        series("s", [
          ["a", 1],
          ["b", 2],
        ]),
      ],
      options({ globalSeriesType: "pie" }),
    ],
    [
      "bubble",
      [
        series(
          "s",
          [
            ["a", 1, 10],
            ["b", 2, 30],
          ],
          ["x", "y", "size"]
        ),
      ],
      options({ globalSeriesType: "bubble" }),
    ],
    [
      "heatmap",
      [
        series(
          "s",
          [
            ["mon", "am", 1],
            ["tue", "pm", 4],
          ],
          ["x", "y", "zVal"]
        ),
      ],
      options({ globalSeriesType: "heatmap" }),
    ],
    [
      "box",
      [
        series("s", [
          ["api", 3],
          ["api", 4],
          ["api", 5],
          ["web", 10],
          ["web", 90],
        ]),
      ],
      options({ globalSeriesType: "box" }),
    ],
    [
      "column with error bars",
      [
        series(
          "s",
          [
            ["a", 10, 2],
            ["b", 14, 3],
          ],
          ["x", "y", "yError"]
        ),
      ],
      options({ globalSeriesType: "column" }),
    ],
  ];

  test.each(cases)("%s draws", (_name, chartData, chartOptions) => {
    const { svg } = render(chartData, chartOptions);

    expect(svg.startsWith("<svg")).toBe(true);
    expect(drawnMarks(svg)).toBeGreaterThan(0);
  });

  test("a box draws its outliers as points beside the box", () => {
    const points: any[][] = [1, 2, 3, 4, 5, 6, 7, 8, 9, 100].map((value) => ["api", value]);
    const { svg, built } = render([series("s", points)], options({ globalSeriesType: "box" }));

    expect(built.option.series.map((s: any) => s.type)).toEqual(["boxplot", "custom"]);
    expect(drawnMarks(svg)).toBeGreaterThan(1);
  });

  test("error bars reach the canvas: three lines per point, over and above the bars", () => {
    const points: any[][] = [
      ["a", 10],
      ["b", 14],
      ["c", 9],
    ];
    const withErrors = points.map((point, index) => [...point, index + 1]);

    const plain = render([series("s", points)], options({ globalSeriesType: "column" }));
    const annotated = render([series("s", withErrors, ["x", "y", "yError"])], options({ globalSeriesType: "column" }));

    // A cap, a stem and a cap for each of the three points.
    expect(drawnMarks(annotated.svg) - drawnMarks(plain.svg)).toBe(9);
  });

  test("an error bar is centred on the bar it annotates, however many series there are", () => {
    // The custom series is positioned in data space while bars are packed into
    // the category band, so this is the assertion that the packing maths is
    // right. It caught the marks landing 18px beside their bars.
    for (let count = 1; count <= 5; count += 1) {
      const chartData = [];
      for (let index = 0; index < count; index += 1) {
        chartData.push(series(`s${index}`, [["a", 10 + index, 2]], ["x", "y", "yError"]));
      }
      const { svg } = render(chartData, options({ globalSeriesType: "column" }));

      const barCentres = svg
        .split(/(?=<path)/)
        .filter((element) => element.includes('ecmeta_ssr_type="chart"'))
        .map((element) => element.match(/d="M([\d.-]+) [\d.-]+l([\d.-]+) 0/))
        .filter(Boolean)
        .map((match: any) => parseFloat(match[1]) + parseFloat(match[2]) / 2);

      const capCentres = Array.from(svg.matchAll(/d="M([\d.]+) ([\d.]+)L([\d.]+) \2"/g))
        .map((match) => ({
          centre: (parseFloat(match[1]) + parseFloat(match[3])) / 2,
          width: Math.abs(parseFloat(match[3]) - parseFloat(match[1])),
        }))
        // The axis and grid lines are horizontal too, and much wider than a cap.
        .filter((line) => line.width < 40)
        .map((line) => line.centre);

      const distinct = (values: number[]) =>
        Array.from(new Set(values.map((v) => v.toFixed(1))))
          .map(Number)
          .sort();

      const bars = distinct(barCentres);
      const caps = distinct(capCentres);

      expect(bars).toHaveLength(count);
      expect(caps).toHaveLength(count);
      bars.forEach((bar, index) => expect(Math.abs(bar - caps[index])).toBeLessThan(0.3));
    }
  });
});

describe("Visualizations -> Chart -> ECharts -> registration", () => {
  // The renders above use the full ECharts build, so they pass whether or not
  // we registered a series type. The app uses a tree-shaken barrel, where an
  // unregistered type draws nothing. Checking the barrel's source is crude, but
  // it is the one thing the render tests structurally cannot see.
  const source = fs.readFileSync(path.join(__dirname, "../../echarts/index.ts"), "utf8");

  test.each([
    ["column", "BarChart"],
    ["line", "LineChart"],
    ["area", "LineChart"],
    ["scatter", "ScatterChart"],
    ["bubble", "ScatterChart"],
    ["pie", "PieChart"],
    ["heatmap", "HeatmapChart"],
    ["box", "BoxplotChart"],
  ])("%s needs %s registered", (_type, chartModule) => {
    expect(source).toContain(chartModule);
  });

  test("error bars need the custom series, and heatmaps need visualMap", () => {
    expect(source).toContain("CustomChart");
    expect(source).toContain("VisualMapComponent");
  });
});

/*
  Two things you cannot see in an option object, only in what gets drawn.

  Both were reported from screenshots, and both are about position rather
  than data: an axis whose tick gaps were uneven, and an axis name sitting
  on top of the legend.
*/
describe("what the drawn axis looks like", () => {
  /** Absolute y: ECharts puts text inside a translated group. */
  function textAt(svg: string) {
    return Array.from(svg.matchAll(/<text\b([^>]*)>([^<]*)<\/text>/g)).map((m: any) => {
      const attrs = m[1] as string;
      const own = /\sy="([-\d.]+)"/.exec(attrs);
      const moved = /transform="[^"]*translate\(\s*([-\d.]+)[ ,]+([-\d.]+)/.exec(attrs);
      return {
        y: (own ? parseFloat(own[1]) : 0) + (moved ? parseFloat(moved[2]) : 0),
        text: (m[2] as string).trim(),
      };
    });
  }

  const moment = require("moment"); // eslint-disable-line global-require

  function daily(days: number) {
    const start = moment.utc("2026-08-10T00:00:00Z");
    return Array.from({ length: days }, (_, d) => [start.clone().add(d, "days"), 100 + d]);
  }

  /*
    ECharts anchors one tick rhythm to the data and another to each month,
    and draws both -- so a 90-day axis came out "15, 22, 29, 5, 8, 15",
    weekly except where a month turned and the step was three days. A month
    is not a whole number of weeks, so the two can never agree.
  */
  test("every gap between time ticks is the same", () => {
    const { svg } = render(
      [{ ...series("revenue", daily(90)), type: "line" }],
      options({ globalSeriesType: "line", xAxis: { type: "-", labels: { enabled: true } } })
    );

    const dates = textAt(svg)
      .map((t) => moment.utc(t.text, "D MMM", true))
      .filter((m: any) => m.isValid())
      .map((m: any) => m.valueOf())
      .sort((a: number, b: number) => a - b);

    expect(dates.length).toBeGreaterThan(4);
    const gaps = dates.slice(1).map((at: number, i: number) => at - dates[i]);
    expect(new Set(gaps).size).toBe(1);
  });

  // Asserted on the ticks rather than the drawing: a narrow chart thins
  // its labels, which is `hideOverlap` doing its job -- it drops alternate
  // ones, so the gaps stay equal and the first label may not survive.
  test("and the ticks start where the data starts, not some way in", () => {
    const { built } = render(
      [{ ...series("revenue", daily(90)), type: "line" }],
      options({ globalSeriesType: "line", xAxis: { type: "-", labels: { enabled: true } } })
    );

    const ticks = built.option.xAxis.axisLabel.customValues;

    expect(ticks[0]).toBe(Date.parse("2026-08-10T00:00:00Z"));
    expect(new Set(ticks.slice(1).map((at: number, i: number) => at - ticks[i])).size).toBe(1);
  });

  /*
    The name is drawn `nameGap` below the axis plus its own height, about
    42px, while only 24 was reserved for the labels. The missing room came
    out of the legend, which the name then sat on.
  */
  test("the x axis name clears the legend below it", () => {
    const data = ["a", "b", "c", "d"].map((name, i) => ({
      ...series(
        name,
        [1, 2, 3].map((x) => [`cat${x}`, x * (i + 1)])
      ),
      type: "line",
    }));
    const { svg } = render(
      data,
      options({
        globalSeriesType: "line",
        xAxis: { type: "category", title: { text: "the x axis name" }, labels: { enabled: true } },
        legend: { enabled: true, placement: "below" },
      })
    );

    const texts = textAt(svg);
    const name = texts.find((t) => t.text === "the x axis name");
    const legendTop = Math.min(...texts.filter((t) => ["a", "b", "c", "d"].includes(t.text)).map((t) => t.y));

    expect(name).toBeDefined();
    // A line of this text is about 12px tall, so anything under that is a
    // collision however it is measured.
    expect(legendTop - (name as any).y).toBeGreaterThan(14);
  });
});
