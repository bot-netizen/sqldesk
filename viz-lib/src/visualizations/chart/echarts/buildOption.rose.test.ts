import buildOption from "./buildOption";
import getOptions from "../getOptions";

/*
  The rose is a pie with equal angles and the value in the radius. It is one
  option on the pie rather than a visualization of its own, so what matters is
  that turning it on changes the drawing and leaves every pie saved before it
  exactly as it was.
*/

const chartData = [
  {
    name: "revenue",
    type: "pie",
    data: [
      { x: "North", y: 100, $raw: { x: "North", y: 100 } },
      { x: "South", y: 60, $raw: { x: "South", y: 60 } },
      { x: "East", y: 20, $raw: { x: "East", y: 20 } },
    ],
  },
];

function pie(overrides: any = {}) {
  const options = getOptions({ globalSeriesType: "pie", ...overrides });
  return buildOption(chartData, options).option.series[0];
}

describe("the pie's rose style", () => {
  test("a pie is a pie unless the rose is chosen", () => {
    const series = pie();
    expect(series.roseType).toBeUndefined();
    // One radius, not a ring.
    expect(typeof series.radius).toBe("string");
  });

  test("a pie saved before the option existed is still a pie", () => {
    // The option is absent entirely, not set to "pie".
    const options = getOptions({ globalSeriesType: "pie" });
    delete (options as any).pieStyle;
    const series = buildOption(chartData, options).option.series[0];
    expect(series.roseType).toBeUndefined();
  });

  test("the rose gives every slice the same angle and puts the value in the radius", () => {
    expect(pie({ pieStyle: "rose" }).roseType).toBe("area");
  });

  test("the rose has a floor for its slices to stand on", () => {
    // From zero, the smallest slice is a needle and unreadable.
    const radius = pie({ pieStyle: "rose" }).radius;
    expect(Array.isArray(radius)).toBe(true);
    expect(parseFloat(radius[0])).toBeGreaterThan(0);
    expect(parseFloat(radius[1])).toBeGreaterThan(parseFloat(radius[0]));
  });

  test("the slices themselves are unchanged", () => {
    // Only the drawing changes: the same names, values and colours.
    const asPie = pie();
    const asRose = pie({ pieStyle: "rose" });
    expect(asRose.data).toEqual(asPie.data);
  });

  test("the rose reaches as far out as the pie does", () => {
    const asPie = parseFloat(pie().radius);
    const asRose = parseFloat(pie({ pieStyle: "rose" }).radius[1]);
    expect(asRose).toBe(asPie);
  });
});
