import getOptions from "../getOptions";
import buildOption from "./buildOption";
import { DEFAULT_HEAT_RAMP } from "./heatRamps";
import { normalizeSeriesTypes } from "./utils";

function options(overrides: any = {}) {
  return getOptions({ sortX: false, ...overrides });
}

describe("Visualizations -> Chart -> ECharts -> bubble", () => {
  function bubbleSeries(points: [any, any, any][]) {
    return [
      {
        name: "sales",
        type: "column",
        data: points.map(([x, y, size]) => ({ x, y, size, $raw: { x, y, size } })),
      },
    ];
  }

  test("bubbles keep their own x values and carry the size as a third number", () => {
    const built = buildOption(
      bubbleSeries([
        ["a", 1, 10],
        ["b", 2, 20],
      ]),
      options({ globalSeriesType: "bubble" })
    );
    const [series] = built.option.series;

    expect(series.type).toBe("scatter");
    expect(series.data).toEqual([
      ["a", 1, 10],
      ["b", 2, 20],
    ]);
  });

  test("diameter sizemode uses the value directly", () => {
    const built = buildOption(
      bubbleSeries([["a", 1, 10]]),
      options({ globalSeriesType: "bubble", sizemode: "diameter", coefficient: 2 })
    );

    expect(built.option.series[0].symbolSize(["a", 1, 10])).toBe(20);
  });

  test("area sizemode converts area to a diameter", () => {
    // Plotly treats the number as an area, ECharts symbolSize is a diameter.
    // Without converting, an area-mode chart draws bubbles wildly too large.
    const built = buildOption(
      bubbleSeries([["a", 1, Math.PI * 25]]),
      options({ globalSeriesType: "bubble", sizemode: "area" })
    );

    expect(built.option.series[0].symbolSize(["a", 1, Math.PI * 25])).toBeCloseTo(10, 6);
  });

  test("a missing size does not produce NaN", () => {
    const built = buildOption(bubbleSeries([["a", 1, null]]), options({ globalSeriesType: "bubble" }));

    expect(built.option.series[0].symbolSize(["a", 1, null])).toBe(0);
  });

  test("bubbles are never stacked", () => {
    const built = buildOption(
      bubbleSeries([["a", 1, 5]]),
      options({ globalSeriesType: "bubble", series: { stacking: "stack" } })
    );

    expect(built.option.series[0].stack).toBeUndefined();
  });
});

describe("Visualizations -> Chart -> ECharts -> heatmap", () => {
  function heatSeries(points: [any, any, any][]) {
    return [
      {
        name: "grid",
        type: "column",
        data: points.map(([x, y, zVal]) => ({ x, y, zVal, $raw: { x, y, zVal } })),
      },
    ];
  }

  const heatOptions = (overrides: any = {}) => options({ globalSeriesType: "heatmap", ...overrides });

  test("builds x/y category axes and index-addressed cells", () => {
    const built = buildOption(
      heatSeries([
        ["mon", "am", 1],
        ["tue", "pm", 4],
      ]),
      heatOptions()
    );

    expect(built.option.xAxis.data).toEqual(["mon", "tue"]);
    expect(built.option.yAxis.data).toEqual(["am", "pm"]);
    expect(built.option.series[0].data).toEqual([
      [0, 0, 1],
      [1, 1, 4],
    ]);
  });

  test("the colour scale spans zero to the largest value", () => {
    const built = buildOption(
      heatSeries([
        ["a", "x", 3],
        ["b", "y", 9],
      ]),
      heatOptions()
    );

    expect(built.option.visualMap.max).toBe(9);
    expect(built.option.visualMap.min).toBe(0);
  });

  test("a custom scheme uses the author's two colours", () => {
    const built = buildOption(
      heatSeries([["a", "x", 1]]),
      heatOptions({ colorScheme: "Custom...", heatMinColor: "#000000", heatMaxColor: "#ffffff" })
    );

    expect(built.option.visualMap.inRange.color).toEqual(["#000000", "#ffffff"]);
  });

  test("a saved Plotly scale name keeps that scale's colours", () => {
    // ECharts ships no named scales, so an unrecognised name would silently
    // recolour every existing heatmap. Viridis runs dark purple to yellow.
    const built = buildOption(heatSeries([["a", "x", 1]]), heatOptions({ colorScheme: "Viridis" }));
    const ramp = built.option.visualMap.inRange.color;

    expect(ramp[0]).toBe("#440154");
    expect(ramp[ramp.length - 1]).toBe("#fde725");
  });

  test("an unknown scheme falls back to the default ramp instead of breaking", () => {
    const built = buildOption(heatSeries([["a", "x", 1]]), heatOptions({ colorScheme: "NotAScale" }));

    expect(built.option.visualMap.inRange.color).toEqual(DEFAULT_HEAT_RAMP);
  });

  test("sorting and reversing the axes is honoured", () => {
    const built = buildOption(
      heatSeries([
        ["b", "2", 1],
        ["a", "1", 2],
      ]),
      heatOptions({ sortX: true, sortY: true, reverseY: true })
    );

    expect(built.option.xAxis.data).toEqual(["a", "b"]);
    expect(built.option.yAxis.data).toEqual(["2", "1"]);
  });

  test("cells with no value read as zero rather than breaking the scale", () => {
    const built = buildOption(heatSeries([["a", "x", null]]), heatOptions());

    expect(built.option.series[0].data).toEqual([[0, 0, 0]]);
  });

  test("the signature tracks both axes, so a new row replaces instead of tweening", () => {
    const before = buildOption(heatSeries([["a", "x", 1]]), heatOptions());
    const sameShape = buildOption(heatSeries([["a", "x", 5]]), heatOptions());
    const newRow = buildOption(
      heatSeries([
        ["a", "x", 1],
        ["a", "y", 2],
      ]),
      heatOptions()
    );

    expect(sameShape.signature).toBe(before.signature);
    expect(newRow.signature).not.toBe(before.signature);
  });
});

describe("Visualizations -> Chart -> ECharts -> correcting a saved chart's types", () => {
  const normalize = (options: any) => normalizeSeriesTypes({ seriesOptions: {}, ...options });

  test("bubble and heatmap are drawn as themselves", () => {
    expect(normalize({ globalSeriesType: "bubble" }).globalSeriesType).toBe("bubble");
    expect(normalize({ globalSeriesType: "heatmap" }).globalSeriesType).toBe("heatmap");
    expect(normalize({ globalSeriesType: "box" }).globalSeriesType).toBe("box");
  });

  test("a chart saved as custom becomes a column, rather than an empty canvas", () => {
    // "custom" was Plotly-only and there is nothing left to run its JavaScript.
    // It also happens to name a real ECharts series, so leaving it alone would
    // draw nothing at all instead of failing visibly.
    expect(normalize({ globalSeriesType: "custom" }).globalSeriesType).toBe("column");
  });

  test("a type nobody has ever heard of becomes a column too", () => {
    expect(normalize({ globalSeriesType: "hexbin" }).globalSeriesType).toBe("column");
    expect(normalize({ globalSeriesType: undefined }).globalSeriesType).toBe("column");
  });

  test("an unusable series override falls back to the chart's own type", () => {
    const options = normalize({ globalSeriesType: "line", seriesOptions: { a: { type: "custom" } } });

    expect(options.seriesOptions.a.type).toBe("line");
  });

  test("a whole-chart type cannot be mixed into a cartesian chart", () => {
    // The renderer branches on the global type for these, so a lone box or
    // heatmap series inside a bar chart would emit a series ECharts cannot pair
    // with the axes it has been given.
    const mixed = (type: string) => normalize({ globalSeriesType: "column", seriesOptions: { a: { type } } });

    expect(mixed("box").seriesOptions.a.type).toBe("column");
    expect(mixed("heatmap").seriesOptions.a.type).toBe("column");
    expect(mixed("pie").seriesOptions.a.type).toBe("column");
  });

  test("a cartesian series inside a whole-chart type is corrected the same way", () => {
    expect(normalize({ globalSeriesType: "box", seriesOptions: { a: { type: "line" } } }).seriesOptions.a.type).toBe(
      "box"
    );
  });

  test("overrides that make sense are left exactly as they were", () => {
    const options = normalize({ globalSeriesType: "column", seriesOptions: { a: { type: "line", color: "#abc" } } });

    expect(options.seriesOptions.a).toEqual({ type: "line", color: "#abc" });
  });

  test("a series with no type of its own is untouched", () => {
    const options = normalize({ globalSeriesType: "column", seriesOptions: { a: { color: "#abc" } } });

    expect(options.seriesOptions.a).toEqual({ color: "#abc" });
  });
});
