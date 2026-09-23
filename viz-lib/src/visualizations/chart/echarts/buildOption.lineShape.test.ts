import getOptions from "../getOptions";
import buildOption from "./buildOption";

/*
  Line Shape, and why every shape has to state every property it controls.

  Options are pushed into a live chart with `setOption(next, { notMerge })`,
  and `notMerge` is false whenever the data's shape has not changed -- which
  is exactly the case when somebody only changes a dropdown. ECharts then
  *merges* the new series options over the old ones, so a property the new
  option simply leaves out keeps whatever the previous one set.

  That is how choosing Spline after Horizontal-Vertical left the chart drawn
  as a staircase: `step: "end"` was still there, because only the "hv" branch
  ever mentioned `step`. Saying `smooth: true` did not unsay it.

  So the rule pinned here is: for any shape, every property the setting owns
  is set to something definite, never left undefined.
*/

function options(overrides: any = {}) {
  return getOptions({ globalSeriesType: "line", ...overrides });
}

const DATA = [
  {
    name: "revenue",
    type: "line",
    data: [
      { x: 1, y: 1250, $raw: { x: 1, y: 1250 } },
      { x: 2, y: 890, $raw: { x: 2, y: 890 } },
    ],
  },
];

const lineFor = (lineShape: string) => buildOption(DATA, options({ lineShape })).option.series[0];

const seriesWith = (overrides: any) => buildOption(DATA, options(overrides)).option.series[0];

describe("Visualizations -> Chart -> ECharts -> line shape", () => {
  test("linear is a plain line", () => {
    const line = lineFor("linear");

    expect(line.smooth).toBe(false);
    expect(line.step).toBe(false);
  });

  test("spline curves", () => {
    const line = lineFor("spline");

    expect(line.smooth).toBe(true);
    expect(line.step).toBe(false);
  });

  test("horizontal-vertical steps at the end of each segment", () => {
    const line = lineFor("hv");

    expect(line.step).toBe("end");
    expect(line.smooth).toBe(false);
  });

  test("vertical-horizontal steps at the start of each segment", () => {
    // Never handled at all before this: choosing it drew a plain line, which
    // is what Linear already does.
    const line = lineFor("vh");

    expect(line.step).toBe("start");
    expect(line.smooth).toBe(false);
  });

  test.each(["linear", "spline", "hv", "vh"])(
    "%s states both properties, so a merge cannot keep the old one",
    (shape) => {
      const line = lineFor(shape);

      expect(line.smooth).toBeDefined();
      expect(line.step).toBeDefined();
    }
  );

  test("changing shape replaces the previous one rather than adding to it", () => {
    // The reported bug, as arithmetic: what a merge of the second over the
    // first would leave behind.
    const before = lineFor("hv");
    const after = lineFor("spline");
    const merged = { ...before, ...after };

    expect(merged.step).toBe(false);
    expect(merged.smooth).toBe(true);
  });
});

/*
  The same fault, in the two other places it can reach a user.

  `globalSeriesType` is part of the signature, so switching Line to Column
  forces a full replace and the line-only properties go with it. Stacking and
  data labels are *not* in the signature: toggling either changes nothing
  about the data's shape, so the chart is updated by merge and a property the
  new option omits survives.
*/
describe("Visualizations -> Chart -> ECharts -> settings that a merge could strand", () => {
  test("stacking off says so, rather than leaving the chart stacked", () => {
    const stacked = seriesWith({ series: { stacking: "stack" } });
    const unstacked = seriesWith({ series: { stacking: null } });

    expect(stacked.stack).toBe("total");
    expect(unstacked.stack).toBeNull();
    expect({ ...stacked, ...unstacked }.stack).toBeNull();
  });

  test("data labels off says so, rather than leaving them showing", () => {
    const labelled = seriesWith({ showDataLabels: true });
    const plain = seriesWith({ showDataLabels: false });

    expect(labelled.label.show).toBe(true);
    expect(plain.label.show).toBe(false);
    expect({ ...labelled, ...plain }.label.show).toBe(false);
  });
});
