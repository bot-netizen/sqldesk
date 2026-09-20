import { toNumber } from "../shared/valueOptions";

/*
  Working out the spokes of a radar, and how far out each one reaches.

  The scaling is the whole argument of a radar chart. Measures on shared
  spokes only mean anything if each spoke's scale is stated, and getting it
  wrong makes an honest-looking shape out of nothing.
*/

export interface Spoke {
  name: string;
  /** How far out the spoke runs. */
  max: number;
  /** Where it starts; below zero when some value is negative. */
  min: number;
}

export type ScaleMode = "per-spoke" | "shared";

/** Every row's value for one column, skipping what does not read as a number. */
function columnValues(rows: any[], column: string): number[] {
  const values: number[] = [];
  (rows || []).forEach((row) => {
    const n = toNumber(row ? row[column] : null);
    if (n !== null && Number.isFinite(n)) {
      values.push(n);
    }
  });
  return values;
}

/**
 * The ends of each spoke.
 *
 * "per-spoke" gives each measure its own scale, which is the only way to put
 * revenue and a satisfaction score on the same chart; the shape then says how
 * each measure compares against the others' best, not against an absolute.
 *
 * "shared" puts every spoke on one scale, which is what you want when the
 * measures are in the same units and the differences between them are the
 * point.
 */
export default function buildSpokes(rows: any[], columns: string[], mode: ScaleMode): Spoke[] {
  const perColumn = columns.map((name) => {
    const values = columnValues(rows, name);
    return { name, values };
  });

  const round = (value: number) => {
    // A spoke ending on the largest value puts that point exactly on the rim,
    // where it is hard to read; a little headroom, rounded to something
    // legible, keeps the shape inside the web.
    if (value <= 0) {
      return 0;
    }
    const magnitude = Math.pow(10, Math.floor(Math.log10(value)));
    return Math.ceil((value * 1.05) / (magnitude / 2)) * (magnitude / 2);
  };

  if (mode === "shared") {
    const all = perColumn.flatMap((c) => c.values);
    const max = all.length ? round(Math.max(...all)) : 1;
    const min = all.length ? Math.min(0, ...all) : 0;
    return columns.map((name) => ({ name, max: max || 1, min }));
  }

  return perColumn.map(({ name, values }) => {
    if (!values.length) {
      return { name, max: 1, min: 0 };
    }
    const max = round(Math.max(...values));
    return { name, max: max || 1, min: Math.min(0, ...values) };
  });
}
