import getOptions from "../getOptions";
import buildOption from "./buildOption";

/*
  A donut is a pie with the middle taken out.

  It was the one shape the pie could not make: `rose` already set an inner
  radius, but a rose is a different chart -- equal angles with the value in
  the radius -- so reaching for it to get a hole gave you the wrong
  encoding.
*/
function pie(style?: string) {
  const data = [
    {
      name: "s",
      type: "pie",
      data: [
        { x: "a", y: 1, $raw: {} },
        { x: "b", y: 2, $raw: {} },
      ],
    },
  ];
  return buildOption(data, getOptions({ globalSeriesType: "pie", sortX: false, ...(style ? { pieStyle: style } : {}) }))
    .option.series[0];
}

describe("the shape of a pie", () => {
  test("a plain pie is solid: one radius, no hole", () => {
    expect(pie()).toMatchObject({ radius: "65%" });
  });

  test("a donut keeps the pie's angles and opens the middle", () => {
    const built = pie("donut");

    expect(built.radius).toEqual(["39%", "65%"]);
    // The giveaway that it is still a pie and not a rose: no roseType.
    expect(built.roseType).toBeUndefined();
  });

  test("a rose is still a rose, with its own tighter centre", () => {
    const built = pie("rose");

    expect(built.radius).toEqual(["16%", "65%"]);
    expect(built.roseType).toBe("area");
  });
});
