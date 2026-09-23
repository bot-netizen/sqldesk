/**
 * What a real ECharts instance keeps when options are merged into it.
 *
 * The other tests here check the shape of the option object we build. That
 * cannot catch the fault this file exists for, because the fault is not in
 * what we build -- it is in what ECharts still has from last time.
 *
 * Options go in with `setOption(next, { notMerge })`, and `notMerge` is false
 * whenever the data's shape is unchanged, which is every time somebody only
 * changes a setting. ECharts then merges, so a property the new option leaves
 * out keeps its previous value. Choosing Spline after Horizontal-Vertical left
 * `step: "end"` in place and the chart stayed a staircase.
 *
 * Asserting against the live instance rather than against our own object is
 * the point: it is the only way to know that saying `step: false` actually
 * unsays `step: "end"`, and that `stack: null` actually unstacks.
 *
 * Uses ECharts' CommonJS build for the same reason render.test.ts does.
 */
import buildOption from "./buildOption";
import getOptions from "../getOptions";

// eslint-disable-next-line @typescript-eslint/no-var-requires
const echarts = require("echarts");

function options(overrides: any = {}) {
  return getOptions({ sortX: false, globalSeriesType: "line", ...overrides });
}

const DATA = [
  {
    name: "revenue",
    type: "line",
    data: [
      { x: 1, y: 1250, $raw: { x: 1, y: 1250 } },
      { x: 2, y: 890, $raw: { x: 2, y: 890 } },
      { x: 3, y: 2100, $raw: { x: 3, y: 2100 } },
    ],
  },
];

/**
 * Put one option in, then another the way a settings change does, and report
 * what the chart ended up with.
 */
function afterChanging(first: any, second: any) {
  const chart = echarts.init(null, null, { renderer: "svg", ssr: true, width: 600, height: 400 });
  try {
    chart.setOption(buildOption(DATA, options(first)).option, { notMerge: true });
    // notMerge: false -- what useEChart does when the data's shape has not
    // changed, which is the case for every one of these settings.
    chart.setOption(buildOption(DATA, options(second)).option, { notMerge: false });
    return chart.getOption().series[0];
  } finally {
    chart.dispose();
  }
}

describe("Visualizations -> Chart -> ECharts -> changing a setting on a live chart", () => {
  test("spline after horizontal-vertical is a curve, not a staircase", () => {
    // The reported bug, against the real thing.
    const series = afterChanging({ lineShape: "hv" }, { lineShape: "spline" });

    expect(series.smooth).toBe(true);
    expect(series.step).toBe(false);
  });

  test("linear after vertical-horizontal is a plain line", () => {
    const series = afterChanging({ lineShape: "vh" }, { lineShape: "linear" });

    expect(series.step).toBe(false);
    expect(series.smooth).toBe(false);
  });

  test("horizontal-vertical after spline is a staircase, not a curve", () => {
    const series = afterChanging({ lineShape: "spline" }, { lineShape: "hv" });

    expect(series.step).toBe("end");
    expect(series.smooth).toBe(false);
  });

  test("turning stacking off actually unstacks", () => {
    const series = afterChanging({ series: { stacking: "stack" } }, { series: { stacking: null } });

    expect(series.stack).toBeFalsy();
  });

  test("turning data labels off actually hides them", () => {
    const series = afterChanging({ showDataLabels: true }, { showDataLabels: false });

    expect(series.label.show).toBe(false);
  });

  test("a setting that is left alone survives the change", () => {
    // The merge is not the enemy -- it is what lets ECharts animate from the
    // old values to the new. This pins that the fix did not turn it off.
    const series = afterChanging(
      { lineShape: "hv", showDataLabels: true },
      { lineShape: "spline", showDataLabels: true }
    );

    expect(series.label.show).toBe(true);
  });
});
