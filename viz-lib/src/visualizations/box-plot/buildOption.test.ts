import buildOption from "./buildOption";

function data(columns: string[], rows: any[]) {
  return { columns: columns.map((name) => ({ name })), rows };
}

describe("Visualizations -> Boxplot (deprecated) -> the option", () => {
  test("each column becomes its own box", () => {
    // This is what distinguishes the deprecated visualization from the Chart's
    // box type, where the boxes come from grouping rows by a category.
    const built = buildOption(
      data(
        ["latency", "size"],
        [
          { latency: 1, size: 10 },
          { latency: 2, size: 20 },
          { latency: 3, size: 30 },
        ]
      ),
      {}
    );
    const [box] = built.option.series;

    expect(built.option.xAxis.data).toEqual(["latency", "size"]);
    expect(box.type).toBe("boxplot");
    expect(box.data).toHaveLength(2);
    expect(box.data[0][2]).toBe(2); // median of 1,2,3
    expect(box.data[1][2]).toBe(20);
  });

  test("outliers are drawn beside the box", () => {
    const rows = [1, 2, 3, 4, 5, 6, 7, 8, 9, 100].map((latency) => ({ latency }));
    const built = buildOption(data(["latency"], rows), {});
    const scatter = built.option.series.find((s: any) => s.type === "scatter");

    expect(scatter.data).toEqual([[0, 100]]);
  });

  test("a column with nothing numeric in it is left out, not held open", () => {
    // It used to keep its place with a null, and ECharts' boxplot series
    // reads `.value` off every item it is handed -- so any result with a text
    // or date column beside its numbers took the whole widget down.
    const built = buildOption(
      data(
        ["label", "v"],
        [
          { label: "n/a", v: 1 },
          { label: "also n/a", v: 3 },
        ]
      ),
      {}
    );
    const [box] = built.option.series;

    expect(built.option.xAxis.data).toEqual(["v"]);
    // One box, for the one column that had numbers in it.
    expect(box.data).toHaveLength(1);
    expect(box.data[0][2]).toBe(2); // median of 1 and 3
  });

  test("outliers are placed against the boxes drawn, not the columns returned", () => {
    // With the text column dropped, the numeric one is box zero.
    const rows = [1, 2, 3, 4, 5, 6, 7, 8, 9, 100].map((latency) => ({ note: "x", latency }));
    const built = buildOption(data(["note", "latency"], rows), {});
    const scatter = built.option.series.find((s: any) => s.type === "scatter");

    expect(built.option.xAxis.data).toEqual(["latency"]);
    expect(scatter.data).toEqual([[0, 100]]);
  });

  test("nothing numeric at all says so rather than drawing an empty grid", () => {
    const built = buildOption(data(["label"], [{ label: "n/a" }]), {});
    expect(built.problem).toBe("No numeric column to draw a box from.");
  });

  test("non-numeric values are skipped rather than poisoning the quartiles", () => {
    const built = buildOption(data(["v"], [{ v: 1 }, { v: "oops" }, { v: 3 }]), {});
    const [box] = built.option.series;

    expect(box.data[0][2]).toBe(2); // median of 1 and 3
  });

  test("the axis labels the editor sets are used", () => {
    const built = buildOption(data(["v"], [{ v: 1 }]), { xAxisLabel: "Columns", yAxisLabel: "Milliseconds" });

    expect(built.option.xAxis.name).toBe("Columns");
    expect(built.option.yAxis.name).toBe("Milliseconds");
  });

  test("the columns are the shape, so new values for the same columns tween", () => {
    const before = buildOption(data(["v"], [{ v: 1 }, { v: 2 }]), {});
    const sameShape = buildOption(data(["v"], [{ v: 5 }, { v: 9 }]), {});
    const newColumn = buildOption(data(["v", "w"], [{ v: 1, w: 2 }]), {});

    expect(sameShape.signature).toBe(before.signature);
    expect(newColumn.signature).not.toBe(before.signature);
  });
});

describe("Visualizations -> Boxplot (deprecated) -> room for the axis names", () => {
  // `containLabel` reserves space for axis labels but not for an axis name, so
  // a rotated y-axis title otherwise runs off the left edge of the canvas.
  test("a y-axis label widens the left margin", () => {
    const without = buildOption(data(["v"], [{ v: 1 }]), {});
    const withLabel = buildOption(data(["v"], [{ v: 1 }]), { yAxisLabel: "Milliseconds" });

    expect(withLabel.option.grid.left).toBeGreaterThan(without.option.grid.left);
  });

  test("an x-axis label deepens the bottom margin", () => {
    const without = buildOption(data(["v"], [{ v: 1 }]), {});
    const withLabel = buildOption(data(["v"], [{ v: 1 }]), { xAxisLabel: "Stage" });

    expect(withLabel.option.grid.bottom).toBeGreaterThan(without.option.grid.bottom);
  });
});
