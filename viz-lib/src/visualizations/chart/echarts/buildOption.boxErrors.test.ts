import getOptions from "../getOptions";
import buildOption from "./buildOption";
import { boxStats, quantile } from "./boxplot";
import { barCentreOffset } from "./errorBars";

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

describe("Visualizations -> Chart -> ECharts -> box", () => {
  const boxOptions = (overrides: any = {}) => options({ globalSeriesType: "box", ...overrides });

  describe("quartiles", () => {
    test("uses linear interpolation, the definition Plotly's box defaults to", () => {
      // R type 7 on 1..4: Q1 = 1.75, median = 2.5, Q3 = 3.25. A different
      // definition (nearest rank, say) would give 2 / 2.5 / 3 and shift every
      // box that already exists.
      const sorted = [1, 2, 3, 4];

      expect(quantile(sorted, 0.25)).toBeCloseTo(1.75, 10);
      expect(quantile(sorted, 0.5)).toBeCloseTo(2.5, 10);
      expect(quantile(sorted, 0.75)).toBeCloseTo(3.25, 10);
    });

    test("a single value is its own quartiles", () => {
      expect(quantile([7], 0.25)).toBe(7);
      expect(quantile([7], 0.75)).toBe(7);
    });

    test("an empty set has no quantile rather than a wrong one", () => {
      expect(quantile([], 0.5)).toBeNaN();
    });
  });

  describe("the five numbers", () => {
    test("whiskers stop at the furthest point inside 1.5 IQR, not at the extremes", () => {
      // 1..9 plus a far outlier. Q1 = 3, Q3 = 7, IQR = 4, upper fence = 13.
      const stats: any = boxStats([1, 2, 3, 4, 5, 6, 7, 8, 9, 100]);

      expect(stats.median).toBeCloseTo(5.5, 10);
      expect(stats.high).toBe(9);
      expect(stats.outliers).toEqual([100]);
    });

    test("with no outliers the whiskers reach the data range", () => {
      const stats: any = boxStats([10, 20, 30]);

      expect(stats.low).toBe(10);
      expect(stats.high).toBe(30);
      expect(stats.outliers).toEqual([]);
    });

    test("non-numeric values are dropped rather than poisoning the quartiles", () => {
      const stats: any = boxStats([1, NaN, 2, null as any, 3]);

      expect(stats.median).toBe(2);
    });

    test("a category with nothing in it has no box", () => {
      expect(boxStats([])).toBeNull();
    });
  });

  describe("the series it builds", () => {
    test("rows sharing an x become one box", () => {
      const built = buildOption(
        [
          series("latency", [
            ["api", 1],
            ["api", 2],
            ["api", 3],
            ["web", 10],
            ["web", 20],
            ["web", 30],
          ]),
        ],
        boxOptions()
      );
      const [box] = built.option.series;

      expect(box.type).toBe("boxplot");
      expect(built.option.xAxis.data).toEqual(["api", "web"]);
      expect(box.data).toHaveLength(2);
      // [low, q1, median, q3, high]
      expect(box.data[0][2]).toBe(2);
      expect(box.data[1][2]).toBe(20);
    });

    test("an outlier is drawn on the box's own centre line, as Plotly drew it", () => {
      const points: any[][] = [1, 2, 3, 4, 5, 6, 7, 8, 9, 100].map((value) => ["api", value]);
      const built = buildOption([series("latency", points)], boxOptions());
      const cloud = built.option.series.find((s: any) => s.type === "custom");

      // [categoryIndex, value, offset, jitter] -- no offset, no jitter.
      expect(cloud.data).toEqual([[0, 100, 0, 0]]);
    });

    test('"Show All Points" draws every value, moved off the box so both stay readable', () => {
      const points: any[][] = [1, 2, 3].map((value) => ["api", value]);
      const built = buildOption([series("latency", points)], boxOptions({ showpoints: true }));
      const cloud = built.option.series.find((s: any) => s.type === "custom");

      expect(cloud.data.map((point: any) => [point[0], point[1]])).toEqual([
        [0, 1],
        [0, 2],
        [0, 3],
      ]);
      // Every point is pushed to the same side of the box...
      expect(cloud.data.every((point: any) => point[2] < 0)).toBe(true);
      // ...and spread, so equal values do not hide behind one another.
      expect(new Set(cloud.data.map((point: any) => point[3])).size).toBe(3);
    });

    test("the spread is stable, so points do not crawl on every refresh", () => {
      const points: any[][] = [1, 2, 3].map((value) => ["api", value]);
      const first = buildOption([series("latency", points)], boxOptions({ showpoints: true }));
      const second = buildOption([series("latency", points)], boxOptions({ showpoints: true }));

      const jitter = (built: any) =>
        built.option.series.find((s: any) => s.type === "custom").data.map((p: any) => p[3]);
      expect(jitter(first)).toEqual(jitter(second));
    });

    test("a category no series has data for still holds its slot", () => {
      const built = buildOption(
        [
          series("a", [
            ["x1", 1],
            ["x1", 2],
          ]),
          series("b", [
            ["x2", 5],
            ["x2", 6],
          ]),
        ],
        boxOptions()
      );
      const [first, second] = built.option.series.filter((s: any) => s.type === "boxplot");

      expect(built.option.xAxis.data).toEqual(["x1", "x2"]);
      expect(first.data[1]).toBeNull();
      expect(second.data[0]).toBeNull();
    });

    test("numeric x values still group, because a box is a distribution per category", () => {
      const built = buildOption(
        [
          series("a", [
            [1, 10],
            [1, 20],
            [2, 5],
          ]),
        ],
        boxOptions({ xAxis: { type: "linear", labels: { enabled: true } } })
      );

      expect(built.option.xAxis.type).toBe("category");
      // Category values are strings throughout the renderer, numeric bins included.
      expect(built.option.xAxis.data).toEqual(["1", "2"]);
    });
  });
});

describe("Visualizations -> Chart -> ECharts -> error bars", () => {
  const withErrors = (points: any[][]) => series("revenue", points, ["x", "y", "yError"]);

  test("an errors column adds a custom series, because ECharts ships no error-bar series", () => {
    const built = buildOption([withErrors([["a", 10, 2]])], options({ globalSeriesType: "column" }));
    const error = built.option.series.find((s: any) => s.type === "custom");

    expect(error.id).toBe("series:revenue:error");
    expect(typeof error.renderItem).toBe("function");
    expect(error.data).toEqual([["a", 10, 2, 0]]);
  });

  test("no errors column means no extra series at all", () => {
    const built = buildOption([series("revenue", [["a", 10]])], options({ globalSeriesType: "column" }));

    expect(built.option.series.filter((s: any) => s.type === "custom")).toEqual([]);
  });

  test("a zero error draws nothing, rather than a flat mark on every bar", () => {
    const built = buildOption([withErrors([["a", 10, 0]])], options({ globalSeriesType: "column" }));

    expect(built.option.series.filter((s: any) => s.type === "custom")).toEqual([]);
  });

  test("aggregated rows sum their errors along with their values", () => {
    const built = buildOption(
      [
        withErrors([
          ["a", 10, 2],
          ["a", 5, 3],
        ]),
      ],
      options({ globalSeriesType: "column" })
    );
    const error = built.option.series.find((s: any) => s.type === "custom");

    expect(error.data).toEqual([["a", 15, 5, 0]]);
  });

  test("the error follows the y axis its series was assigned to", () => {
    const built = buildOption(
      [withErrors([["a", 10, 2]])],
      options({ globalSeriesType: "column", seriesOptions: { revenue: { type: "column", yAxis: 1 } } })
    );
    const error = built.option.series.find((s: any) => s.type === "custom");

    expect(error.yAxisIndex).toBe(1);
  });

  test("stacked bars put the mark at the running total, where the bar top actually is", () => {
    const built = buildOption(
      [withErrors([["a", 10, 1]]), series("cost", [["a", 4, 2]], ["x", "y", "yError"])],
      options({ globalSeriesType: "column", series: { stacking: "stack" } })
    );
    const [first, second] = built.option.series.filter((s: any) => s.type === "custom");

    expect(first.data[0][1]).toBe(10);
    expect(second.data[0][1]).toBe(14);
  });

  describe("where a bar actually sits inside its category", () => {
    test("a lone bar is centred, so its error needs no offset", () => {
      expect(barCentreOffset(0, 1)).toBe(0);
    });

    test("two bars sit either side of the centre, symmetrically", () => {
      const left = barCentreOffset(0, 2);
      const right = barCentreOffset(1, 2);

      expect(left).toBeLessThan(0);
      expect(right).toBeGreaterThan(0);
      expect(left + right).toBeCloseTo(0, 10);
    });

    test("the bars stay inside their category band", () => {
      for (let count = 1; count <= 6; count += 1) {
        for (let index = 0; index < count; index += 1) {
          expect(Math.abs(barCentreOffset(index, count))).toBeLessThan(0.5);
        }
      }
    });

    test("each series gets its own slot, so errors land on different bars", () => {
      const built = buildOption(
        [withErrors([["a", 10, 2]]), series("cost", [["a", 4, 1]], ["x", "y", "yError"])],
        options({ globalSeriesType: "column" })
      );
      const [first, second] = built.option.series.filter((s: any) => s.type === "custom");

      expect(first.data[0][3]).not.toBe(second.data[0][3]);
    });
  });
});

describe("Visualizations -> Chart -> ECharts -> the value axis baseline", () => {
  const axis = (built: any) => built.option.yAxis[0];

  test("a bar chart starts at zero, because a bar's length is its value", () => {
    const built = buildOption(
      [
        series("s", [
          ["a", 100],
          ["b", 104],
        ]),
      ],
      options({ globalSeriesType: "column" })
    );

    expect(axis(built).scale).toBe(false);
  });

  test("a line chart may crop its axis, where the shape is what carries meaning", () => {
    const built = buildOption(
      [
        series("s", [
          ["a", 100],
          ["b", 104],
        ]),
      ],
      options({ globalSeriesType: "line" })
    );

    expect(axis(built).scale).toBe(true);
  });

  test("one bar series among lines is still enough to pin the axis to zero", () => {
    const built = buildOption(
      [series("a", [["x", 100]]), series("b", [["x", 104]])],
      options({ globalSeriesType: "line", seriesOptions: { b: { type: "column" } } })
    );

    expect(axis(built).scale).toBe(false);
  });
});
