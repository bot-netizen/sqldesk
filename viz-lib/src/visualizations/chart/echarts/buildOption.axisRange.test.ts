import getOptions from "../getOptions";
import buildOption from "./buildOption";

/*
  The min and max somebody types into the axis editor.

  The editor has written `rangeMin` and `rangeMax` into a chart's options
  since the fork and nothing ever read them, so setting either did nothing --
  on every chart type, not only the bubble chart it was noticed on. These
  tests are the record of that: each one fails if the options stop reaching
  the axis.
*/
function options(overrides: any = {}) {
  return getOptions({ sortX: false, ...overrides });
}

function series() {
  return [
    {
      name: "sales",
      type: "column",
      data: [
        { x: 1, y: 10, $raw: { x: 1, y: 10 } },
        { x: 2, y: 90, $raw: { x: 2, y: 90 } },
      ],
    },
  ];
}

function yAxes(built: any) {
  return Array.isArray(built.option.yAxis) ? built.option.yAxis : [built.option.yAxis];
}

describe("Visualizations -> Chart -> ECharts -> axis range", () => {
  test("a minimum reaches the y axis", () => {
    const built = buildOption(series(), options({ yAxis: [{ type: "linear", rangeMin: 5 }, { type: "linear" }] }));

    expect(yAxes(built)[0].min).toBe(5);
  });

  test("a maximum reaches the y axis", () => {
    const built = buildOption(series(), options({ yAxis: [{ type: "linear", rangeMax: 100 }, { type: "linear" }] }));

    expect(yAxes(built)[0].max).toBe(100);
  });

  test("zero is a bound like any other", () => {
    // The trap that makes a half-fix: `rangeMin ? ... : ...` drops 0, which
    // is the most commonly wanted minimum there is.
    const built = buildOption(series(), options({ yAxis: [{ type: "linear", rangeMin: 0 }, { type: "linear" }] }));

    expect(yAxes(built)[0].min).toBe(0);
  });

  test("one bound on its own leaves the other automatic", () => {
    const built = buildOption(series(), options({ yAxis: [{ type: "linear", rangeMin: 5 }, { type: "linear" }] }));

    expect(yAxes(built)[0].min).toBe(5);
    expect(yAxes(built)[0].max).toBeUndefined();
  });

  test("an axis with no bounds set carries none", () => {
    const built = buildOption(series(), options());

    expect(yAxes(built)[0].min).toBeUndefined();
    expect(yAxes(built)[0].max).toBeUndefined();
  });

  test("a bubble chart's y axis takes them, which is where this was noticed", () => {
    const built = buildOption(
      [
        {
          name: "sales",
          type: "column",
          data: [{ x: 1, y: 50, size: 10, $raw: { x: 1, y: 50, size: 10 } }],
        },
      ],
      options({
        globalSeriesType: "bubble",
        yAxis: [{ type: "linear", rangeMin: 0, rangeMax: 100 }, { type: "linear" }],
      })
    );

    expect(yAxes(built)[0].min).toBe(0);
    expect(yAxes(built)[0].max).toBe(100);
  });

  test("the second y axis takes its own bounds", () => {
    const built = buildOption(
      series(),
      options({
        yAxis: [
          { type: "linear", rangeMin: 0 },
          { type: "linear", rangeMin: -50, rangeMax: 50 },
        ],
      })
    );

    expect(yAxes(built)[1].min).toBe(-50);
    expect(yAxes(built)[1].max).toBe(50);
  });

  test("a numeric x axis takes them too, for a scatter", () => {
    const built = buildOption(
      series(),
      options({ globalSeriesType: "scatter", xAxis: { type: "linear", rangeMin: 0, rangeMax: 10 } })
    );
    const xAxis = Array.isArray(built.option.xAxis) ? built.option.xAxis[0] : built.option.xAxis;

    expect(xAxis.min).toBe(0);
    expect(xAxis.max).toBe(10);
  });

  test("a category x axis does not, because there min and max are indexes", () => {
    // ECharts reads them as positions in the category list, so a value typed
    // by somebody meaning "start at 1,000" would silently crop the chart to
    // its thousandth category.
    const built = buildOption(
      [
        {
          name: "sales",
          type: "column",
          data: [
            { x: "a", y: 1, $raw: { x: "a", y: 1 } },
            { x: "b", y: 2, $raw: { x: "b", y: 2 } },
          ],
        },
      ],
      options({ xAxis: { type: "category", rangeMin: 1, rangeMax: 2 } })
    );
    const xAxis = Array.isArray(built.option.xAxis) ? built.option.xAxis[0] : built.option.xAxis;

    expect(xAxis.min).toBeUndefined();
    expect(xAxis.max).toBeUndefined();
  });
});

/*
  The axis name, and the room it needs.

  `containLabel` reserves space for the tick labels and not for the axis name,
  which ECharts draws `nameGap` further out again -- so on a chart whose
  labels are short the name was cut off by the edge of the canvas. Reported
  while building a chart, which is where the preview is narrowest.
*/
describe("Visualizations -> Chart -> ECharts -> room for the axis name", () => {
  function grid(built: any) {
    return Array.isArray(built.option.grid) ? built.option.grid[0] : built.option.grid;
  }

  test("a named y axis gets room on the left for its name", () => {
    const named = buildOption(series(), options({ yAxis: [{ type: "linear", title: { text: "Revenue" } }, {}] }));
    const bare = buildOption(series(), options());

    expect(grid(named).left).toBeGreaterThan(grid(bare).left);
  });

  test("an unnamed chart keeps every pixel of its width", () => {
    expect(grid(buildOption(series(), options())).left).toBe(12);
  });

  test("a title saved as a plain string counts as a name", () => {
    // Saved charts carry either shape; the one that is not an object was the
    // one that slipped through when this was spelled out by hand in three
    // places.
    const built = buildOption(series(), options({ yAxis: [{ type: "linear", title: "Revenue" }, {}] }));

    expect(grid(built).left).toBeGreaterThan(12);
    const axis = Array.isArray(built.option.yAxis) ? built.option.yAxis[0] : built.option.yAxis;
    expect(axis.name).toBe("Revenue");
  });

  test("sideways, the room goes to the axis that is actually on the left", () => {
    // Horizontal swaps them: the category axis -- described by the x axis
    // settings -- is the one down the left-hand side.
    const built = buildOption(
      series(),
      options({ swappedAxes: true, globalSeriesType: "column", xAxis: { type: "category", title: { text: "Region" } } })
    );

    expect(grid(built).left).toBeGreaterThan(12);
  });
});
