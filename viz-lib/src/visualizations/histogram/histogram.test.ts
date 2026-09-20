import buildOption from "./buildOption";
import getOptions from "./getOptions";

/*
  The binning arithmetic is covered in binning.test.ts. What is left here is
  the translation into a chart: that the bars touch (which is the difference
  between a histogram and a bar chart), that percent mode divides by the
  values counted rather than the rows returned, and that a result nothing can
  be drawn from says so instead of drawing an empty grid.
*/

const columns = [
  { name: "latency_ms", type: "float" },
  { name: "service", type: "string" },
];

function rowsOf(values: any[]) {
  return values.map((v) => ({ latency_ms: v, service: "api" }));
}

function build(values: any[], overrides: any = {}) {
  const data = { columns, rows: rowsOf(values) };
  return buildOption(data, getOptions({ valueColumn: "latency_ms", ...overrides }, data));
}

describe("the histogram", () => {
  test("draws one bar per bin, with the bars touching", () => {
    const built = build([0, 1, 2, 3, 4, 5, 6, 7, 8, 9], { binCount: 5 });
    const series = built.option.series[0];
    expect(series.type).toBe("bar");
    expect(series.data).toHaveLength(5);
    // Gaps here would make it a bar chart of ranges, not a distribution.
    expect(series.barCategoryGap).toBe("0%");
    expect(series.barGap).toBe("0%");
  });

  test("bar heights are the counts", () => {
    const built = build([1, 1, 1, 5, 9], { binCount: 2 });
    expect(built.option.series[0].data).toEqual([3, 2]);
  });

  test("percent mode measures against the values counted, not the rows returned", () => {
    // Eight rows, two of which hold nothing numeric: the bars are shares of
    // the six that could be binned, and add up to 100.
    const built = build([1, 1, 1, 9, 9, 9, null, "n/a"], { binCount: 2, countMode: "percent" });
    expect(built.option.series[0].data).toEqual([50, 50]);
  });

  test("says how many rows it had to leave out, rather than silently dropping them", () => {
    const built = build([1, 2, 3, null, "n/a"], { binCount: 2 });
    expect(built.note).toBe("2 rows had no number in “latency_ms”.");
    expect(built.problem).toBeNull();
  });

  test("counts one skipped row in the singular", () => {
    expect(build([1, 2, null], { binCount: 2 }).note).toBe("1 row had no number in “latency_ms”.");
  });

  test("says nothing when every row was usable", () => {
    expect(build([1, 2, 3], { binCount: 2 }).note).toBeNull();
  });

  test("the axis labels the lower edge of each bin", () => {
    const built = build([0, 10], { binCount: 2 });
    expect(built.option.xAxis.data).toEqual(["0", "5"]);
    expect(built.option.xAxis.name).toBe("latency_ms");
  });

  test("bin edges get enough decimals to tell them apart", () => {
    // Four bins across 0..0.4 are 0.1 wide; at the default zero decimals every
    // label would read "0".
    const built = build([0, 0.1, 0.2, 0.3, 0.4], { binCount: 4, valueFormat: { style: "number", decimals: 0 } });
    expect(new Set(built.option.xAxis.data).size).toBe(4);
  });

  test("the mean is drawn where it falls across the bins, not at its raw value", () => {
    // 0..100 in ten bins, mean 50: half way along a ten-category axis is 4.5.
    const values = Array.from({ length: 101 }, (_, i) => i);
    const built = build(values, { binCount: 10, showMean: true });
    const markLine = built.option.series[0].markLine;
    expect(markLine.data[0].xAxis).toBeCloseTo(4.5, 1);
  });

  test("no mean line unless it was asked for", () => {
    expect(build([1, 2, 3], { binCount: 2 }).option.series[0].markLine).toBeUndefined();
  });

  describe("when there is nothing to draw", () => {
    test("no rows", () => {
      const data = { columns, rows: [] };
      const built = buildOption(data, getOptions({ valueColumn: "latency_ms" }, data));
      expect(built.problem).toBe("No rows to show.");
    });

    test("a column that is not in the result", () => {
      const data = { columns, rows: rowsOf([1, 2]) };
      const built = buildOption(data, getOptions({ valueColumn: "gone" }, data));
      expect(built.problem).toBe("Choose a column to bin in the editor.");
    });

    test("a column with no numbers in it", () => {
      const data = { columns, rows: rowsOf([null, "n/a", ""]) };
      const built = buildOption(data, getOptions({ valueColumn: "latency_ms" }, data));
      expect(built.problem).toBe("“latency_ms” holds no numbers to bin.");
    });
  });

  test("new counts in the same bins can tween; different bins redraw", () => {
    const same = build([1, 2, 3, 9], { binCount: 4 }).signature;
    const alsoSame = build([1, 1, 3, 9], { binCount: 4 }).signature;
    const different = build([1, 2, 3, 9], { binCount: 8 }).signature;
    expect(alsoSame).toBe(same);
    expect(different).not.toBe(same);
  });

  test("the tooltip says which end of a bin owns its edge", () => {
    const built = build([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10], { binCount: 2 });
    const tooltip = (index: number) => built.option.tooltip.formatter([{ dataIndex: index }]);
    // Every bin stops short of its upper edge...
    expect(tooltip(0)).toContain("[0, 5)");
    // ...except the last, which includes it, or the 10 would be in no bin.
    expect(tooltip(1)).toContain("[5, 10]");
  });

  test("describes itself for a screen reader", () => {
    const built = build([0, 5, 10], { binCount: 2 });
    expect(built.option.aria.enabled).toBe(true);
    expect(built.option.aria.label.description).toContain("latency_ms");
    expect(built.option.aria.label.description).toContain("3 values in 2 bins");
  });
});

describe("the histogram's options", () => {
  test("a new histogram picks the first numeric column and lets the data choose the bins", () => {
    const options = getOptions({}, { columns, rows: rowsOf([1, 2, 3]) });
    expect(options.valueColumn).toBe("latency_ms");
    expect(options.binCount).toBeNull();
  });

  test("an unusable bin count means let the data choose, rather than one bin", () => {
    const data = { columns, rows: rowsOf([1, 2, 3]) };
    expect(getOptions({ binCount: "" }, data).binCount).toBeNull();
    expect(getOptions({ binCount: undefined }, data).binCount).toBeNull();
    expect(getOptions({ binCount: 12 }, data).binCount).toBe(12);
  });

  test("a saved histogram keeps what it was saved with", () => {
    const saved = { valueColumn: "service", binCount: 7, countMode: "percent", color: "critical", showMean: true };
    expect(getOptions(saved, { columns, rows: [] })).toMatchObject(saved);
  });
});
