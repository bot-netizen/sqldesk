/*
  The results a visualization actually meets, as opposed to the one it was
  written against.

  Every shape here has broken something at some point: an empty result, a
  column of nulls, decimals arriving as strings from a driver that reports no
  type, a single row, a column with no spread in it. They are shared by the
  option matrix and the drawing matrix so that every visualization is put
  through all of them rather than whichever its author thought of.
*/

export interface Shape {
  name: string;
  columns: { name: string; type?: string | null }[];
  rows: any[];
}

const COLUMNS = [
  { name: "label", type: "string" },
  { name: "status", type: "string" },
  { name: "value", type: "float" },
  { name: "other", type: "integer" },
  { name: "target", type: "integer" },
  { name: "started", type: "datetime" },
  { name: "ended", type: "datetime" },
];

function row(i: number, over: any = {}) {
  const start = new Date(Date.UTC(2024, 2, 5, 9 + (i % 12)));
  const end = new Date(start.getTime() + 30 * 60000);
  return {
    label: ["North", "South", "East", "West"][i % 4],
    status: ["ok", "warn", "down"][i % 3],
    value: 10 + i * 7.5,
    other: 3 + i,
    target: 100,
    started: start.toISOString(),
    ended: end.toISOString(),
    ...over,
  };
}

const normalRows = Array.from({ length: 8 }, (_, i) => row(i));

export const SHAPES: Shape[] = [
  { name: "an ordinary result", columns: COLUMNS, rows: normalRows },

  // Nothing came back. Every visualization has to say so rather than draw an
  // empty grid or divide by the number of rows.
  { name: "no rows", columns: COLUMNS, rows: [] },

  // One row means no spread, no previous value and no second category.
  { name: "a single row", columns: COLUMNS, rows: [row(0)] },

  // A column that is entirely null: min and max are the same nothing.
  {
    name: "every value null",
    columns: COLUMNS,
    rows: Array.from({ length: 4 }, (_, i) => row(i, { value: null, other: null, status: null, started: null })),
  },

  // Drivers that report no type hand back decimals as strings, and "" for a
  // missing value rather than null.
  {
    name: "numbers arriving as text",
    columns: COLUMNS.map((c) => ({ ...c, type: null })),
    rows: [
      row(0, { value: "10.5" }),
      row(1, { value: "" }),
      row(2, { value: "not a number" }),
      row(3, { value: "42" }),
    ],
  },

  // Negative values: scales that assume a floor of zero draw these off the
  // chart, or not at all.
  {
    name: "negative values",
    columns: COLUMNS,
    rows: normalRows.map((r, i) => ({ ...r, value: -r.value * (i % 2 ? 1 : 2) })),
  },

  // A mix of both sides of zero, which is where baselines and stacking break.
  {
    name: "values either side of zero",
    columns: COLUMNS,
    rows: normalRows.map((r, i) => ({ ...r, value: i % 2 ? r.value : -r.value })),
  },

  // No spread at all: a scale from n to n divides by zero.
  { name: "no spread", columns: COLUMNS, rows: normalRows.map((r) => ({ ...r, value: 42, other: 42 })) },

  // Zero everywhere, which is not the same as no spread: shares and
  // percentages divide by the total.
  { name: "all zeroes", columns: COLUMNS, rows: normalRows.map((r) => ({ ...r, value: 0, other: 0 })) },

  // Numbers big enough to need a compact format, and small enough to need
  // decimals, in the same column.
  {
    name: "very large and very small together",
    columns: COLUMNS,
    rows: [row(0, { value: 0.0000123 }), row(1, { value: 9.87e12 }), row(2, { value: 1 }), row(3, { value: -4.2e9 })],
  },

  // Nothing numeric to measure.
  {
    name: "no numeric column",
    columns: [
      { name: "label", type: "string" },
      { name: "status", type: "string" },
    ],
    rows: [
      { label: "North", status: "ok" },
      { label: "South", status: "down" },
    ],
  },

  // One column, which is all some queries return.
  { name: "a single column", columns: [{ name: "value", type: "float" }], rows: [{ value: 1 }, { value: 2 }] },

  // Labels that are not strings, and labels that repeat.
  {
    name: "awkward labels",
    columns: COLUMNS,
    rows: [row(0, { label: 2024 }), row(1, { label: null }), row(2, { label: "" }), row(3, { label: "North" })],
  },

  // More rows than any of these will draw comfortably.
  { name: "many rows", columns: COLUMNS, rows: Array.from({ length: 400 }, (_, i) => row(i)) },
];

/** Widget sizes a visualization has to survive, including silly ones. */
export const SIZES = [
  { name: "a dashboard tile", width: 340, height: 220 },
  { name: "a full-width strip", width: 1410, height: 140 },
  { name: "a tall narrow column", width: 220, height: 620 },
  { name: "barely there", width: 60, height: 40 },
];
