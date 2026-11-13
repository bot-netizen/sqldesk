import getOptions from "../getOptions";
import buildOption from "./buildOption";

/*
  A line is only a line if its points are joined in x order.

  A category axis has always had this: every series is aligned to one sorted
  category list. A time or value axis had nothing, so the points were joined in
  the order the rows arrived -- and a query with no ORDER BY drew a line running
  backwards and forwards across the chart. A stream query is exactly that case:
  the window comes back in whatever order the engine chose.
*/
function lineOptions(overrides: any = {}) {
  return getOptions({ globalSeriesType: "line", ...overrides });
}

const UNSORTED = [
  {
    name: "north",
    type: "line",
    data: [
      { x: 3000, y: 30 },
      { x: 1000, y: 10 },
      { x: 2000, y: 20 },
    ],
  },
];

function xs(built: any, index = 0) {
  return built.option.series[index].data.map((point: any) => (Array.isArray(point) ? point[0] : point.value[0]));
}

describe("points on a non-category axis", () => {
  test("are joined in x order, whatever order the rows came in", () => {
    const option = buildOption(UNSORTED, lineOptions({ xAxis: { type: "datetime" } }));

    expect(xs(option)).toEqual([1000, 2000, 3000]);
  });

  test("and the y values travel with their own x", () => {
    const option = buildOption(UNSORTED, lineOptions({ xAxis: { type: "datetime" } }));
    const ys = option.option.series[0].data.map((point: any) => (Array.isArray(point) ? point[1] : point.value[1]));

    expect(ys).toEqual([10, 20, 30]);
  });

  test("a numeric axis is sorted as numbers, not as text", () => {
    const option = buildOption(
      [
        {
          name: "a",
          type: "line",
          data: [
            { x: 100, y: 1 },
            { x: 9, y: 2 },
            { x: 80, y: 3 },
          ],
        },
      ],
      lineOptions({ xAxis: { type: "linear" } })
    );

    expect(xs(option)).toEqual([9, 80, 100]);
  });

  // Somebody who turns sorting off is asking to plot a path in the order the
  // rows came -- a trajectory rather than a function of x.
  test("unless sorting was deliberately turned off", () => {
    const option = buildOption(UNSORTED, lineOptions({ sortX: false, xAxis: { type: "datetime" } }));

    expect(xs(option)).toEqual([3000, 1000, 2000]);
  });
});

/*
  Bars put their x on a category axis, which holds it as text -- and text
  order put toggle 11 before toggle 2. Found on a stacked bar chart of
  feature toggles whose bars, with their labels off, all read as the wrong
  toggle.
*/
describe("bars over numbers", () => {
  const TOGGLES = [
    {
      name: "active",
      type: "column",
      data: [1, 2, 3, 7, 11, 12, 20, 25].map((x) => ({ x, y: x })),
    },
  ];

  function categories(built: any) {
    const axis = Array.isArray(built.option.xAxis) ? built.option.xAxis[0] : built.option.xAxis;
    return axis.data;
  }

  test("are in numeric order, not text order", () => {
    const built = buildOption(TOGGLES, getOptions({ globalSeriesType: "column" }));

    expect(categories(built)).toEqual(["1", "2", "3", "7", "11", "12", "20", "25"]);
  });

  test("and each bar keeps its own value", () => {
    const built = buildOption(TOGGLES, getOptions({ globalSeriesType: "column" }));
    const values = built.option.series[0].data.map((point: any) =>
      point && point.value !== undefined ? point.value : point
    );

    expect(values.map((value: any) => (Array.isArray(value) ? value[1] : value))).toEqual([1, 2, 3, 7, 11, 12, 20, 25]);
  });

  test("numbers that arrive as text sort as numbers too", () => {
    const asText = [{ ...TOGGLES[0], data: TOGGLES[0].data.map((point) => ({ ...point, x: String(point.x) })) }];
    const built = buildOption(asText, getOptions({ globalSeriesType: "column" }));

    expect(categories(built)).toEqual(["1", "2", "3", "7", "11", "12", "20", "25"]);
  });

  test("names keep the text order they always had", () => {
    const named = [{ name: "a", type: "column", data: ["b", "a10", "a2"].map((x, i) => ({ x, y: i })) }];
    const built = buildOption(named, getOptions({ globalSeriesType: "column" }));

    expect(categories(built)).toEqual(["a10", "a2", "b"]);
  });

  test("reversed, it is the numeric order backwards", () => {
    const built = buildOption(TOGGLES, getOptions({ globalSeriesType: "column", reverseX: true }));

    expect(categories(built)).toEqual(["25", "20", "12", "11", "7", "3", "2", "1"]);
  });
});
