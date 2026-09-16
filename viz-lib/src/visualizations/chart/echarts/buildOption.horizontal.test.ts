import getOptions from "../getOptions";
import buildOption from "./buildOption";

function options(overrides: any = {}) {
  return getOptions({ sortX: false, globalSeriesType: "column", ...overrides });
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

const NUMERIC_X = { xAxis: { type: "linear", labels: { enabled: true } } };

describe("Visualizations -> Chart -> ECharts -> swapped axes", () => {
  describe("on a category axis", () => {
    const data = [
      series("revenue", [
        ["Jan", 1250],
        ["Feb", 890],
      ]),
    ];

    test("upright, the categories are along the bottom", () => {
      const built = buildOption(data, options({ swappedAxes: false }));

      expect(built.option.xAxis.type).toBe("category");
      expect(built.option.xAxis.data).toEqual(["Jan", "Feb"]);
      expect(built.option.yAxis[0].type).toBe("value");
    });

    test("on its side, the categories move to the left", () => {
      const built = buildOption(data, options({ swappedAxes: true }));

      expect(built.option.yAxis[0].type).toBe("category");
      expect(built.option.yAxis[0].data).toEqual(["Jan", "Feb"]);
      expect(built.option.xAxis[0].type).toBe("value");
    });

    test("bare values work either way, because the position comes from the index", () => {
      const upright = buildOption(data, options({ swappedAxes: false }));
      const sideways = buildOption(data, options({ swappedAxes: true }));

      expect(upright.option.series[0].data).toEqual([1250, 890]);
      expect(sideways.option.series[0].data).toEqual([1250, 890]);
    });
  });

  describe("a numeric x axis, which is where the bug was", () => {
    const data = [
      series("revenue", [
        [1, 1250],
        [2, 890],
      ]),
    ];

    test("a bar chart gets a real category axis, because that is what makes bars lie down", () => {
      // ECharts takes a bar's direction from which axis is the category one.
      // With two value axes it draws them upright whatever the data says, so
      // the button appeared to do nothing but relabel the ticks.
      const built = buildOption(data, options({ swappedAxes: true, ...NUMERIC_X }));

      expect(built.option.yAxis[0].type).toBe("category");
      expect(built.option.yAxis[0].data).toEqual(["1", "2"]);
      expect(built.option.series[0].data).toEqual([1250, 890]);
    });

    test("upright, the bar chart is categorical too, so every bar keeps a label", () => {
      const built = buildOption(data, options({ swappedAxes: false, ...NUMERIC_X }));

      expect(built.option.xAxis.type).toBe("category");
      expect(built.option.xAxis.data).toEqual(["1", "2"]);
    });

    test("a line keeps both value axes, and its points are written the other way round", () => {
      // Nothing about a line needs a category axis, so it keeps the numeric one
      // and the pair itself is what has to swap.
      const upright = buildOption(data, options({ globalSeriesType: "line", swappedAxes: false, ...NUMERIC_X }));
      const sideways = buildOption(data, options({ globalSeriesType: "line", swappedAxes: true, ...NUMERIC_X }));

      expect(upright.option.series[0].data).toEqual([
        [1, 1250],
        [2, 890],
      ]);
      expect(sideways.option.series[0].data).toEqual([
        [1250, 1],
        [890, 2],
      ]);
      expect(sideways.option.yAxis[0].type).toBe("value");
    });

    test("a bubble keeps its size as the third number either way round", () => {
      const bubbles = [
        series(
          "revenue",
          [
            [1, 1250, 10],
            [2, 890, 20],
          ],
          ["x", "y", "size"]
        ),
      ];
      const sideways = buildOption(bubbles, options({ globalSeriesType: "bubble", swappedAxes: true, ...NUMERIC_X }));

      expect(sideways.option.series[0].data).toEqual([
        [1250, 1, 10],
        [890, 2, 20],
      ]);
    });
  });

  describe("the axis a series is assigned to", () => {
    const twoSeries = [series("a", [["Jan", 1]]), series("b", [["Jan", 2]])];
    const secondAxis = { seriesOptions: { b: { type: "column", yAxis: 1 } } };

    test("upright, the second measure axis is on the right", () => {
      const built = buildOption(twoSeries, options({ swappedAxes: false, ...secondAxis }));

      expect(built.option.yAxis).toHaveLength(2);
      expect(built.option.yAxis[1].position).toBe("right");
      expect(built.option.series[1].yAxisIndex).toBe(1);
    });

    test("on its side, it is along the top, and the series still reaches it", () => {
      // There is only ever one category axis, so the assignment has to move to
      // the x axis. Left as a yAxisIndex it would point at an axis that is not
      // there.
      const built = buildOption(twoSeries, options({ swappedAxes: true, ...secondAxis }));

      expect(built.option.xAxis).toHaveLength(2);
      expect(built.option.xAxis[1].position).toBe("top");
      expect(built.option.series[1].xAxisIndex).toBe(1);
      expect(built.option.series[1].yAxisIndex).toBe(0);
    });
  });

  describe("reading the measure back out", () => {
    const data = [series("revenue", [[1, 1250]])];

    test("the data label reads the measure, not the category, on its side", () => {
      const sideways = buildOption(data, options({ swappedAxes: true, showDataLabels: true, ...NUMERIC_X }));
      const upright = buildOption(data, options({ swappedAxes: false, showDataLabels: true, ...NUMERIC_X }));

      expect(sideways.option.series[0].label.formatter({ value: [1250, 1] })).toBe(
        upright.option.series[0].label.formatter({ value: [1, 1250] })
      );
    });

    test("so does the tooltip", () => {
      const sideways = buildOption(data, options({ swappedAxes: true, ...NUMERIC_X }));
      const upright = buildOption(data, options({ swappedAxes: false, ...NUMERIC_X }));

      const item = (value: any) => ({ seriesName: "revenue", name: "1", value, marker: "" });
      expect(sideways.option.tooltip.formatter([item([1250, 1])])).toBe(
        upright.option.tooltip.formatter([item([1, 1250])])
      );
    });
  });
});
