import getOptions from "../getOptions";
import buildOption from "./buildOption";

function options(overrides: any = {}) {
  return getOptions({ sortX: false, globalSeriesType: "column", ...overrides });
}

function series(name: string, points: any[][], type = "column") {
  return {
    name,
    type,
    data: points.map(([x, y]) => {
      const point: any = { x, y };
      return { ...point, $raw: point };
    }),
  };
}

const VARIANCE = [
  series("variance", [
    ["Jan", 1250],
    ["Feb", -890],
    ["Mar", 0],
    ["Apr", null],
  ]),
];

const RED = "#d64545";
const GREEN = "#2e8b57";

const below = (overrides: any = {}) => ({
  valueThreshold: { enabled: true, value: 0, below: RED, above: null, ...overrides },
});

/** The measure out of a datum, whichever shape it is in. */
function measure(datum: any, horizontal = false) {
  const value = datum && datum.value !== undefined ? datum.value : datum;
  return Array.isArray(value) ? (horizontal ? value[0] : value[1]) : value;
}

const colourOf = (datum: any) => (datum && datum.itemStyle ? datum.itemStyle.color : undefined);

describe("Visualizations -> Chart -> ECharts -> colouring bars by value", () => {
  test("a bar below the breakpoint takes the threshold colour", () => {
    const built = buildOption(VARIANCE, options(below()));
    const data = built.option.series[0].data;

    expect(colourOf(data[1])).toBe(RED);
    expect(measure(data[1])).toBe(-890);
  });

  test("a bar above it keeps the series colour", () => {
    const built = buildOption(VARIANCE, options(below()));
    const data = built.option.series[0].data;

    // Not the threshold colour; whatever the palette gave the series.
    expect(colourOf(data[0])).not.toBe(RED);
    expect(colourOf(data[0])).toMatch(/^#|^rgb/);
  });

  test("a bar exactly at the breakpoint counts as above it", () => {
    // A zero bar has no height to colour, and reading it as a shortfall is
    // wrong. So a threshold of 0 colours negatives only.
    const built = buildOption(VARIANCE, options(below()));

    expect(colourOf(built.option.series[0].data[2])).not.toBe(RED);
  });

  test("both sides can be set", () => {
    const built = buildOption(VARIANCE, options(below({ above: GREEN })));
    const data = built.option.series[0].data;

    expect(colourOf(data[1])).toBe(RED);
    expect(colourOf(data[0])).toBe(GREEN);
    expect(colourOf(data[2])).toBe(GREEN);
  });

  test("the breakpoint does not have to be zero", () => {
    const built = buildOption(VARIANCE, options(below({ value: 1000 })));
    const data = built.option.series[0].data;

    expect(colourOf(data[0])).not.toBe(RED); // 1250
    expect(colourOf(data[1])).toBe(RED); // -890
    expect(colourOf(data[2])).toBe(RED); // 0, now below 1000
  });

  test("a missing value read as zero is coloured as a zero, not as a gap", () => {
    // `missingValuesAsZero` is on by default, so the gap has already become a
    // 0 before any of this runs -- and a 0 at a breakpoint of 0 is above it.
    const built = buildOption(VARIANCE, options(below()));
    const april = built.option.series[0].data[3];

    expect(measure(april)).toBe(0);
    expect(colourOf(april)).not.toBe(RED);
  });

  test("a real gap stays a gap rather than becoming a coloured zero", () => {
    const built = buildOption(VARIANCE, options({ ...below(), missingValuesAsZero: false }));

    expect(built.option.series[0].data[3]).toBeNull();
  });

  /*
    Bars are put on a category axis whatever the data says -- that is what lets
    them lie down -- and a category datum is the bare measure. The one shape
    where a bar carries a pair is a time axis, which keeps its real dates so a
    week with no reading stays a gap.

    That is the only case where the measure is not the datum, and on its side
    the pair is written measure-first. Reading the wrong element colours bars by
    their date, which is every bar or none.
  */
  describe("a bar chart on a time axis, where a datum is a pair", () => {
    const DATED = [
      series("variance", [
        ["2026-01-01", 1250],
        ["2026-02-01", -890],
      ]),
    ];
    const timed = (overrides: any = {}) =>
      options({ ...below(), xAxis: { type: "datetime", labels: { enabled: true } }, ...overrides });

    test("the data really is pairs, or this proves nothing", () => {
      expect(Array.isArray(measure(buildOption(DATED, timed()).option.series[0].data[0], false))).toBe(false);
      expect(buildOption(DATED, timed()).option.xAxis.type).toBe("time");
    });

    test("upright, the measure is the second element", () => {
      const data = buildOption(DATED, timed()).option.series[0].data;

      expect(colourOf(data.find((datum: any) => measure(datum) === -890))).toBe(RED);
      expect(colourOf(data.find((datum: any) => measure(datum) === 1250))).not.toBe(RED);
    });

    test("on its side, it is the first", () => {
      const data = buildOption(DATED, timed({ swappedAxes: true })).option.series[0].data;

      expect(colourOf(data.find((datum: any) => measure(datum, true) === -890))).toBe(RED);
      expect(colourOf(data.find((datum: any) => measure(datum, true) === 1250))).not.toBe(RED);
    });
  });

  describe("when it should do nothing at all", () => {
    /*
      Bare numbers matter: ECharts takes a batched rendering path for a series
      of plain values, and wrapping every point in an object to colour none of
      them would give that up on every chart in the product.
    */
    const isPlain = (data: any[]) => data.every((datum) => datum === null || typeof datum !== "object");

    test("off by default", () => {
      expect(isPlain(buildOption(VARIANCE, options()).option.series[0].data)).toBe(true);
    });

    test("enabled but with no colour chosen", () => {
      const built = buildOption(VARIANCE, options({ valueThreshold: { enabled: true, value: 0 } }));

      expect(isPlain(built.option.series[0].data)).toBe(true);
    });

    test("coloured but switched off", () => {
      const built = buildOption(VARIANCE, options(below({ enabled: false })));

      expect(isPlain(built.option.series[0].data)).toBe(true);
    });

    test("a line chart, which has goal lines for this instead", () => {
      const line = [
        series("variance", [
          ["Jan", 1250],
          ["Feb", -890],
        ]),
      ];
      const built = buildOption(line, options({ ...below(), globalSeriesType: "line" }));

      expect(isPlain(built.option.series[0].data)).toBe(true);
    });
  });
});
