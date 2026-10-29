import getOptions from "../getOptions";
import buildOption from "./buildOption";
import { ROLLUPS, finishRollup, rollupMode, startRollup, addToRollup } from "../rollup";

/*
  A query keyed on region, channel and product returns several rows per
  region. Plot region alone and something has to happen to the duplicates.
  It has always been a sum, silently; this is what lets a chart say
  otherwise -- the average of four conversion rates is a conversion rate,
  their sum is nothing at all.
*/
const ROWS: [string, number | null][] = [
  ["North", 10],
  ["North", 20],
  ["North", 30],
  ["South", 4],
  ["South", 8],
];

function series(rows = ROWS) {
  return [
    {
      name: "sales",
      type: "line",
      data: rows.map(([x, y]) => ({ x, y, $raw: { x, y } })),
    },
  ];
}

function drawn(overrides: any = {}, rows = ROWS) {
  const built = buildOption(series(rows), getOptions({ globalSeriesType: "column", sortX: false, ...overrides }));
  return built.option.series[0].data;
}

describe("Visualizations -> Chart -> rolling up repeated x values", () => {
  describe("the behaviour that was already there", () => {
    test("a chart that says nothing still adds them up", () => {
      expect(drawn()).toEqual([60, 12]);
    });

    test("a chart saved before this existed draws the numbers it always drew", () => {
      // No `rollup` key at all, which is every chart in every database today.
      expect(rollupMode({})).toBe("sum");
      expect(rollupMode({ rollup: undefined })).toBe("sum");
    });

    test("a word this version does not know is a sum, not a blank chart", () => {
      expect(rollupMode({ rollup: "median" })).toBe("sum");
      expect(rollupMode({ rollup: 7 })).toBe("sum");
      expect(drawn({ rollup: "median" })).toEqual([60, 12]);
    });
  });

  describe("choosing something else", () => {
    test("an average divides by the rows at that x", () => {
      expect(drawn({ rollup: "average" })).toEqual([20, 6]);
    });

    test("the lowest and the highest each keep one row's value", () => {
      expect(drawn({ rollup: "min" })).toEqual([10, 4]);
      expect(drawn({ rollup: "max" })).toEqual([30, 8]);
    });

    test("a count is about rows, so it ignores the measure entirely", () => {
      expect(drawn({ rollup: "count" })).toEqual([3, 2]);
    });

    test("every offered mode draws something", () => {
      ROLLUPS.forEach(({ value }) => {
        const points = drawn({ rollup: value });
        expect(points).toHaveLength(2);
        points.forEach((point: any) => expect(point).not.toBeUndefined());
      });
    });
  });

  describe("rows with no number in them", () => {
    const WITH_GAPS: [string, number | null][] = [
      ["North", 10],
      ["North", null],
      ["North", 20],
      ["South", null],
    ];

    /*
      `missingValuesAsZero` is on by default and turns a null into a 0 before
      the roll-up sees it, which is the old behaviour and stays the default.
      With it off, a null is genuinely absent.
    */
    test("by default a missing number is a zero, as it always was", () => {
      expect(drawn({ rollup: "average" }, WITH_GAPS)).toEqual([10, 0]);
    });

    test("with missing values left missing, an average ignores them rather than counting them as zero", () => {
      // 10 and 20 average to 15. Counting the null as a row would give 10,
      // which reads as a third of the traffic vanishing.
      expect(drawn({ rollup: "average", missingValuesAsZero: false }, WITH_GAPS)).toEqual([15, null]);
    });

    test("an x with nothing to draw is a gap, not a zero", () => {
      // Drawing it at zero claims the measure was zero, which is a different
      // and much worse statement than "no reading".
      expect(drawn({ rollup: "sum", missingValuesAsZero: false }, WITH_GAPS)[1]).toBeNull();
      expect(drawn({ rollup: "min", missingValuesAsZero: false }, WITH_GAPS)[1]).toBeNull();
    });

    test("a count still counts a row whose measure is missing", () => {
      // "How many orders in this region" is a question about rows, and an
      // order with no total is still an order.
      expect(drawn({ rollup: "count", missingValuesAsZero: false }, WITH_GAPS)).toEqual([3, 1]);
    });
  });

  describe("what does not roll up", () => {
    test("a scatter keeps every row, because it is a point cloud", () => {
      const built = buildOption(series(), getOptions({ globalSeriesType: "scatter", sortX: false, rollup: "average" }));

      expect(built.option.series[0].data).toHaveLength(ROWS.length);
    });
  });

  describe("the arithmetic on its own", () => {
    test("an empty x has nothing to show but can still be counted", () => {
      const empty = startRollup();

      expect(finishRollup(empty, "sum")).toBeNull();
      expect(finishRollup(empty, "average")).toBeNull();
      expect(finishRollup(empty, "min")).toBeNull();
      expect(finishRollup(empty, "max")).toBeNull();
      expect(finishRollup(empty, "count")).toBe(0);
    });

    test("a value that is not a number is not folded in", () => {
      const state = addToRollup(addToRollup(startRollup(), 5), NaN);

      expect(finishRollup(state, "sum")).toBe(5);
      expect(finishRollup(state, "average")).toBe(5);
      // It was still a row.
      expect(finishRollup(state, "count")).toBe(2);
    });

    test("negatives are kept, so min is the lowest and not the smallest magnitude", () => {
      const state = [3, -7, 1].reduce((acc, n) => addToRollup(acc, n), startRollup());

      expect(finishRollup(state, "min")).toBe(-7);
      expect(finishRollup(state, "max")).toBe(3);
      expect(finishRollup(state, "sum")).toBe(-3);
    });

    test("every mode offered in the editor is one the arithmetic handles", () => {
      const state = addToRollup(startRollup(), 4);

      ROLLUPS.forEach(({ value }) => expect(finishRollup(state, value)).not.toBeUndefined());
    });
  });
});
