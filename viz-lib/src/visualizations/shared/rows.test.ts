import { rowIndex, pickRow } from "./rows";

/*
  Counter has read its "row number" option this way since long before these
  helpers existed, and saved visualizations depend on every one of these
  cases -- particularly the wrap, which is how a counter pointed at row 7 of
  a three-row result keeps showing something.
*/
describe("rowIndex", () => {
  test("1 is the first row and -1 the last", () => {
    expect(rowIndex(1, 3)).toBe(0);
    expect(rowIndex(2, 3)).toBe(1);
    expect(rowIndex(3, 3)).toBe(2);
    expect(rowIndex(-1, 3)).toBe(2);
    expect(rowIndex(-2, 3)).toBe(1);
    expect(rowIndex(-3, 3)).toBe(0);
  });

  test("0 also means the first row", () => {
    expect(rowIndex(0, 3)).toBe(0);
  });

  test("past the end it wraps, from whichever end it was counting", () => {
    expect(rowIndex(4, 3)).toBe(0);
    expect(rowIndex(7, 3)).toBe(0);
    expect(rowIndex(8, 3)).toBe(1);
    expect(rowIndex(-4, 3)).toBe(2);
    expect(rowIndex(-8, 3)).toBe(1);
  });

  test("anything unreadable is the first row", () => {
    // What a saved option holds is whatever the editor put there.
    expect(rowIndex("2", 3)).toBe(1);
    expect(rowIndex("", 3)).toBe(0);
    expect(rowIndex(null, 3)).toBe(0);
    expect(rowIndex(undefined, 3)).toBe(0);
    expect(rowIndex(NaN, 3)).toBe(0);
    expect(rowIndex("third", 3)).toBe(0);
  });

  test("an empty result has no row, rather than row zero of nothing", () => {
    expect(rowIndex(1, 0)).toBe(-1);
    expect(rowIndex(0, 0)).toBe(-1);
    expect(rowIndex(-1, 0)).toBe(-1);
  });
});

describe("pickRow", () => {
  const rows = [{ n: "a" }, { n: "b" }, { n: "c" }];

  test("returns the row rowIndex points at", () => {
    expect(pickRow(rows, 1)).toBe(rows[0]);
    expect(pickRow(rows, -1)).toBe(rows[2]);
    expect(pickRow(rows, 5)).toBe(rows[1]);
  });

  test("returns null rather than reaching past the end", () => {
    expect(pickRow([], 1)).toBeNull();
    expect(pickRow([], 0)).toBeNull();
  });
});
