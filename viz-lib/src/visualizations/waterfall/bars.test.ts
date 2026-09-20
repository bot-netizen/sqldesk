import buildBars, { barsExtent, isTruthy } from "./bars";

/*
  A waterfall is a running total drawn as bars. If the total drifts, every bar
  after the drift is in the wrong place and the chart still looks like a
  perfectly good waterfall -- so the arithmetic is tested here rather than
  left to the eye.
*/

const base = { labelColumn: "step", valueColumn: "amount", totalColumn: "", showTotal: false, totalLabel: "Total" };

function bars(rows: any[], overrides: any = {}) {
  return buildBars({ rows, ...base, ...overrides }).bars;
}

describe("buildBars", () => {
  test("each bar starts where the last one ended", () => {
    const result = bars([
      { step: "Opening", amount: 100 },
      { step: "Sales", amount: 50 },
      { step: "Refunds", amount: -30 },
    ]);
    expect(result.map((b) => [b.from, b.to])).toEqual([
      [0, 100],
      [100, 150],
      [150, 120],
    ]);
  });

  test("a rise goes up and a fall goes down", () => {
    const result = bars([
      { step: "up", amount: 10 },
      { step: "down", amount: -4 },
    ]);
    expect(result.map((b) => b.kind)).toEqual(["rise", "fall"]);
    expect(result[1].from).toBeGreaterThan(result[1].to);
  });

  test("zero is a rise, not a fall", () => {
    // Nothing happened; drawing it red would say something did.
    expect(bars([{ step: "flat", amount: 0 }])[0].kind).toBe("rise");
  });

  test("the running total can go negative and keep going", () => {
    const result = bars([
      { step: "a", amount: 10 },
      { step: "b", amount: -25 },
      { step: "c", amount: 5 },
    ]);
    expect(result.map((b) => b.to)).toEqual([10, -15, -10]);
  });

  test("a total row stands on the baseline and reaches the running total", () => {
    const result = bars(
      [
        { step: "Revenue", amount: 100, total: false },
        { step: "Costs", amount: -40, total: false },
        { step: "Gross", amount: 0, total: true },
        { step: "Tax", amount: -10, total: false },
      ],
      { totalColumn: "total" }
    );
    expect(result[2]).toEqual({ label: "Gross", delta: 60, from: 0, to: 60, kind: "total" });
    // And it does not move the running total: Tax carries on from 60, not 120.
    expect(result[3]).toMatchObject({ from: 60, to: 50 });
  });

  test("an appended total is the level everything adds up to", () => {
    const result = bars(
      [
        { step: "a", amount: 30 },
        { step: "b", amount: -12 },
      ],
      { showTotal: true, totalLabel: "Net" }
    );
    expect(result).toHaveLength(3);
    expect(result[2]).toEqual({ label: "Net", delta: 18, from: 0, to: 18, kind: "total" });
  });

  test("no total bar is appended to an empty result", () => {
    expect(bars([], { showTotal: true })).toEqual([]);
  });

  test("rows with nothing numeric are counted, not placed", () => {
    const built = buildBars({
      ...base,
      rows: [
        { step: "a", amount: 10 },
        { step: "b", amount: null },
        { step: "c", amount: "n/a" },
        { step: "d", amount: "20" },
      ],
    });
    expect(built.skipped).toBe(2);
    // And the ones that remain still chain correctly.
    expect(built.bars.map((b) => [b.from, b.to])).toEqual([
      [0, 10],
      [10, 30],
    ]);
  });

  test("rows are numbered when there is no label column", () => {
    const result = bars([{ amount: 1 }, { amount: 2 }], { labelColumn: "" });
    expect(result.map((b) => b.label)).toEqual(["1", "2"]);
  });

  test("a label that is not a string still labels the bar", () => {
    expect(bars([{ step: 2024, amount: 1 }])[0].label).toBe("2024");
  });
});

describe("barsExtent", () => {
  test("covers every level the bars reach", () => {
    expect(
      barsExtent(
        bars([
          { step: "a", amount: 10 },
          { step: "b", amount: 15 },
        ])
      )
    ).toEqual({ min: 0, max: 25 });
  });

  test("always includes the baseline", () => {
    // Bars that never come near zero still have to be read against it.
    expect(
      barsExtent(
        bars([
          { step: "a", amount: 100 },
          { step: "b", amount: -20 },
        ])
      )
    ).toEqual({ min: 0, max: 100 });
    expect(barsExtent(bars([{ step: "a", amount: -50 }]))).toEqual({ min: -50, max: 0 });
  });

  test("no bars is a flat, empty range rather than infinities", () => {
    expect(barsExtent([])).toEqual({ min: 0, max: 0 });
  });
});

describe("isTruthy", () => {
  test("reads the ways a database says yes", () => {
    [true, 1, -1, "true", "TRUE", "t", "yes", "Y", "1"].forEach((v) => expect(isTruthy(v)).toBe(true));
  });

  test("reads the ways it says no", () => {
    [false, 0, "", "false", "f", "no", "0", null, undefined, "anything else"].forEach((v) =>
      expect(isTruthy(v)).toBe(false)
    );
  });
});
