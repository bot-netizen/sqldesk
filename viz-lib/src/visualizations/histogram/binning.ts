import { toNumber } from "../shared/valueOptions";

/*
  Turning a column of numbers into bins.

  Kept apart from the drawing so the arithmetic can be tested on its own --
  bin edges are the whole visualization, and they are easy to get subtly
  wrong at the ends.
*/

export interface Bin {
  /** Inclusive. */
  from: number;
  /** Exclusive, except for the last bin, which includes its upper edge. */
  to: number;
  count: number;
}

export interface Binned {
  bins: Bin[];
  /** Values that were counted; rows with nothing numeric in them are not. */
  total: number;
  /** Rows skipped because the column held nothing that reads as a number. */
  skipped: number;
}

/** No more than this many bins, however the count was arrived at. */
export const MAX_BINS = 250;

/**
 * How many bins a column deserves when nobody has said.
 *
 * Freedman-Diaconis: bin width is 2 * IQR / n^(1/3), which follows the spread
 * of the middle half of the data and so is not pulled about by outliers the
 * way a range-based rule is. It gives up when the IQR is zero -- half the
 * values identical, which happens with counts and flags -- and Sturges takes
 * over there.
 */
export function suggestBinCount(values: number[]): number {
  const n = values.length;
  if (n < 2) {
    return 1;
  }
  const sorted = [...values].sort((a, b) => a - b);
  const min = sorted[0];
  const max = sorted[n - 1];
  if (max === min) {
    return 1;
  }
  const iqr = quantile(sorted, 0.75) - quantile(sorted, 0.25);
  const width = iqr > 0 ? (2 * iqr) / Math.cbrt(n) : 0;
  const fromWidth = width > 0 ? Math.ceil((max - min) / width) : 0;
  // Sturges, the fallback: log2(n) + 1.
  const sturges = Math.ceil(Math.log2(n)) + 1;
  return clampBinCount(fromWidth > 0 ? fromWidth : sturges);
}

export function clampBinCount(count: unknown): number {
  const n = Math.round(Number(count));
  if (!Number.isFinite(n) || n < 1) {
    return 1;
  }
  return Math.min(n, MAX_BINS);
}

/** The p-th quantile of an already sorted array, interpolating between points. */
function quantile(sorted: number[], p: number): number {
  const position = (sorted.length - 1) * p;
  const lower = Math.floor(position);
  const upper = Math.ceil(position);
  if (lower === upper) {
    return sorted[lower];
  }
  return sorted[lower] + (sorted[upper] - sorted[lower]) * (position - lower);
}

/** Every value in the column that reads as a number, in row order. */
export function readValues(rows: any[], column: string): { values: number[]; skipped: number } {
  const values: number[] = [];
  let skipped = 0;
  (rows || []).forEach((row) => {
    const n = toNumber(row ? row[column] : null);
    if (n === null || !Number.isFinite(n)) {
      skipped += 1;
    } else {
      values.push(n);
    }
  });
  return { values, skipped };
}

/**
 * Bin a column of numbers into `binCount` equal-width bins, or into however
 * many `suggestBinCount` asks for when `binCount` is null.
 */
export default function binValues(values: number[], binCount: number | null, skipped = 0): Binned {
  if (!values.length) {
    return { bins: [], total: 0, skipped };
  }
  const min = Math.min(...values);
  const max = Math.max(...values);

  // Every value identical: one bin holding all of them. Splitting a zero-width
  // range into ten would draw nine empty bars beside one full one.
  if (min === max) {
    return { bins: [{ from: min, to: min, count: values.length }], total: values.length, skipped };
  }

  const count = binCount === null ? suggestBinCount(values) : clampBinCount(binCount);
  const width = (max - min) / count;
  const bins: Bin[] = [];
  for (let i = 0; i < count; i += 1) {
    // The last edge is `max` exactly rather than min + count * width, which
    // floating point does not always land on.
    bins.push({ from: min + i * width, to: i === count - 1 ? max : min + (i + 1) * width, count: 0 });
  }

  values.forEach((value) => {
    // Bins are half-open [from, to) so a value on an edge lands in exactly one
    // of them -- except the maximum, which belongs to the last bin rather than
    // to a bin past the end.
    let index = Math.floor((value - min) / width);
    if (index >= count) {
      index = count - 1;
    }
    if (index < 0) {
      index = 0;
    }
    bins[index].count += 1;
  });

  return { bins, total: values.length, skipped };
}
