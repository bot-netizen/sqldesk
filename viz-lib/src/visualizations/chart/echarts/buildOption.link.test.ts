import getOptions from "../getOptions";
import buildOption, { buildLinkContext, fillLinkTemplate } from "./buildOption";

function series(name: string, points: [any, any][]) {
  return {
    name,
    type: "column",
    data: points.map(([x, y]) => ({ x, y, $raw: { x, y } })),
  };
}

function options(overrides: any = {}) {
  return getOptions({ globalSeriesType: "column", sortX: false, ...overrides });
}

/**
 * Clicking a point opens a URL built from a template. The template's
 * placeholders were never substituted -- the browser was sent to the template
 * as written -- so these cover the filling in, not just the opening.
 */
describe("Visualizations -> Chart -> ECharts -> drill-down links", () => {
  const built = buildOption(
    [
      series("north", [
        ["a", 2],
        ["b", 4],
      ]),
      series("south", [
        ["a", 7],
        ["b", 9],
      ]),
    ],
    options()
  );

  // What ECharts hands a click handler for the second point of the first series.
  const click = { seriesName: "north", seriesIndex: 0, dataIndex: 1, name: "b", value: ["b", 4] };

  test("the clicked point is @@x and @@y", () => {
    const context = buildLinkContext(built.option, click, options());

    expect(context["@@x"]).toBe("b");
    expect(context["@@y"]).toBe(4);
    expect(context["@@name"]).toBe("north");
  });

  test("every series at that position is numbered in configuration order", () => {
    const context = buildLinkContext(built.option, click, options());

    expect(context["@@y1"]).toBe(4);
    expect(context["@@y2"]).toBe(9);
    expect(context["@@x1"]).toBe("b");
    expect(context["@@x2"]).toBe("b");
  });

  test("values are raw, not formatted", () => {
    // A tooltip may say "1.2k"; a URL that says so points at nothing.
    const big = buildOption([series("north", [["a", 1200]])], options());
    const context = buildLinkContext(
      big.option,
      { seriesName: "north", dataIndex: 0, name: "a", value: ["a", 1200] },
      options()
    );

    expect(context["@@y"]).toBe(1200);
  });

  test("a template comes out filled in", () => {
    const context = buildLinkContext(built.option, click, options());

    expect(fillLinkTemplate("https://example.com/{{ @@x }}?v={{ @@y }}", context)).toBe("https://example.com/b?v=4");
  });

  test("an unknown reference leaves an empty string, as the editor says", () => {
    const context = buildLinkContext(built.option, click, options());

    expect(fillLinkTemplate("https://example.com/{{ @@nonsense }}", context)).toBe("https://example.com/");
  });

  test("on a chart on its side the pair is the other way round", () => {
    const swapped = options({ swappedAxes: true });
    const sideways = buildOption([series("north", [["a", 2]])], swapped);
    const context = buildLinkContext(
      sideways.option,
      { seriesName: "north", dataIndex: 0, name: "a", value: [2, "a"] },
      swapped
    );

    expect(context["@@x"]).toBe("a");
    expect(context["@@y"]).toBe(2);
  });
});
