import binValues, { suggestBinCount, clampBinCount, readValues, MAX_BINS } from "./binning";

/*
  Bin edges are the whole histogram: a value counted into the wrong bin, or
  into none at all, is a bar of the wrong height and nothing on screen says so.
  The edge cases below are the ones that actually come up -- a column of
  identical values, a maximum sitting exactly on the last edge, nulls.
*/

function counts(values: number[], binCount: number | null) {
  return binValues(values, binCount).bins.map((b) => b.count);
}

describe("binValues", () => {
  test("splits a range into equal bins and counts what falls in each", () => {
    // 0..10 in ten bins: one value per bin, and the 10 joins the last.
    expect(counts([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 10)).toEqual([1, 1, 1, 1, 1, 1, 1, 1, 1, 2]);
  });

  test("every value is counted exactly once", () => {
    const values = [1, 1.5, 2.25, 3, 7, 7, 7.0001, 9.9, 10];
    [1, 2, 3, 5, 8, 13].forEach((binCount) => {
      const binned = binValues(values, binCount);
      const counted = binned.bins.reduce((sum, b) => sum + b.count, 0);
      expect(counted).toBe(values.length);
      expect(binned.total).toBe(values.length);
    });
  });

  test("a value on a bin edge lands in the bin above it, not both", () => {
    // Edges at 0, 5, 10. The 5 belongs to the second bin only.
    expect(counts([0, 5, 9], 2)).toEqual([1, 2]);
  });

  test("the largest value joins the last bin rather than falling off the end", () => {
    const binned = binValues([0, 10], 5);
    expect(binned.bins[binned.bins.length - 1].count).toBe(1);
    expect(binned.bins.reduce((sum, b) => sum + b.count, 0)).toBe(2);
  });

  test("a column where every value is the same gets one bin, not a row of empties", () => {
    const binned = binValues([7, 7, 7, 7], 10);
    expect(binned.bins).toEqual([{ from: 7, to: 7, count: 4 }]);
  });

  test("bins run from the smallest value to the largest with no gaps", () => {
    const binned = binValues([-3, 0, 2.5, 11], 4);
    expect(binned.bins[0].from).toBe(-3);
    expect(binned.bins[binned.bins.length - 1].to).toBe(11);
    binned.bins.slice(1).forEach((bin, i) => {
      expect(bin.from).toBeCloseTo(binned.bins[i].to, 10);
    });
  });

  test("negative values bin the same way as positive ones", () => {
    expect(counts([-10, -5, 0], 2)).toEqual([1, 2]);
  });

  test("no values means no bins", () => {
    expect(binValues([], 10)).toEqual({ bins: [], total: 0, skipped: 0 });
  });
});

describe("suggestBinCount", () => {
  test("follows the spread of the middle half rather than the outliers", () => {
    // A hundred values packed into 0..10, plus one at 10000. A range-based
    // rule would give one enormous bin and ninety-nine empty ones.
    const packed = Array.from({ length: 100 }, (_, i) => (i % 11) * 1.0);
    const withOutlier = [...packed, 10000];
    expect(suggestBinCount(withOutlier)).toBeGreaterThan(20);
  });

  test("falls back to Sturges when the middle half has no spread at all", () => {
    // Sixteen values, twelve of them identical: the inter-quartile range is
    // zero and Freedman-Diaconis has nothing to divide by.
    const flatMiddle = [0, ...Array(12).fill(5), 20, 30, 40];
    expect(suggestBinCount(flatMiddle)).toBe(Math.ceil(Math.log2(16)) + 1);
  });

  test("one value, or none, is one bin", () => {
    expect(suggestBinCount([])).toBe(1);
    expect(suggestBinCount([4])).toBe(1);
    expect(suggestBinCount([4, 4, 4])).toBe(1);
  });

  test("never suggests more bins than a chart can draw", () => {
    const spread = Array.from({ length: 5000 }, (_, i) => Math.sin(i) * 1000);
    expect(suggestBinCount(spread)).toBeLessThanOrEqual(MAX_BINS);
  });
});

describe("clampBinCount", () => {
  test("keeps a sensible number as it is", () => {
    expect(clampBinCount(20)).toBe(20);
  });

  test("refuses to make no bins, or a fraction of one", () => {
    expect(clampBinCount(0)).toBe(1);
    expect(clampBinCount(-5)).toBe(1);
    expect(clampBinCount(2.4)).toBe(2);
    expect(clampBinCount("nonsense")).toBe(1);
    expect(clampBinCount(null)).toBe(1);
  });

  test("caps a number that would draw more bars than pixels", () => {
    expect(clampBinCount(100000)).toBe(MAX_BINS);
  });
});

describe("readValues", () => {
  test("takes the numbers and counts what it had to leave out", () => {
    const rows = [{ v: 1 }, { v: "2.5" }, { v: null }, { v: "" }, { v: "not a number" }, { v: 3 }];
    expect(readValues(rows, "v")).toEqual({ values: [1, 2.5, 3], skipped: 3 });
  });

  test("a missing column skips every row rather than counting zeroes", () => {
    // Zeroes would be a histogram of a column that is not there, which reads
    // as a real result.
    expect(readValues([{ a: 1 }, { a: 2 }], "b")).toEqual({ values: [], skipped: 2 });
  });

  test("no rows is not an error", () => {
    expect(readValues([], "v")).toEqual({ values: [], skipped: 0 });
    expect(readValues(null as any, "v")).toEqual({ values: [], skipped: 0 });
  });
});
