import { toNumber } from "../shared/valueOptions";

/*
  Turning rows of changes into the bars of a waterfall.

  Kept apart from the drawing so the arithmetic can be tested on its own. A
  waterfall is only useful if the running total is right, and a running total
  that drifts looks exactly like one that does not.
*/

export type BarKind = "rise" | "fall" | "total";

export interface WaterfallBar {
  label: string;
  /** The change this bar shows. For a total, the level it stands at. */
  delta: number;
  /** Where the bar starts, in value space. */
  from: number;
  /** Where it ends. Below `from` for a fall. */
  to: number;
  kind: BarKind;
}

/** A value that reads as "yes" in a column marking total rows. */
export function isTruthy(value: unknown): boolean {
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value === "number") {
    return value !== 0;
  }
  if (typeof value === "string") {
    const v = value.trim().toLowerCase();
    return v === "true" || v === "t" || v === "yes" || v === "y" || v === "1";
  }
  return false;
}

export interface BuildBarsInput {
  rows: any[];
  labelColumn: string;
  valueColumn: string;
  /** Rows where this column is true stand from the baseline, not on the last bar. */
  totalColumn: string;
  /** Append a final bar for the level everything adds up to. */
  showTotal: boolean;
  totalLabel: string;
}

export interface BuiltBars {
  bars: WaterfallBar[];
  /** Rows whose value column held nothing numeric, and so could not be placed. */
  skipped: number;
}

/**
 * Walk the rows, carrying a running total.
 *
 * A normal row is a change: its bar starts where the last one ended. A row
 * marked as a total is a checkpoint: its bar stands on the baseline and reaches
 * the running total, which is what makes "Revenue, Costs, Gross, Tax, Net"
 * read correctly rather than stacking the subtotal on top of itself.
 */
export default function buildBars({
  rows,
  labelColumn,
  valueColumn,
  totalColumn,
  showTotal,
  totalLabel,
}: BuildBarsInput): BuiltBars {
  const bars: WaterfallBar[] = [];
  let running = 0;
  let skipped = 0;

  (rows || []).forEach((row, index) => {
    const value = toNumber(row ? row[valueColumn] : null);
    if (value === null || !Number.isFinite(value)) {
      skipped += 1;
      return;
    }
    const label = labelColumn && row && row[labelColumn] !== undefined ? String(row[labelColumn]) : String(index + 1);
    const isTotal = !!totalColumn && isTruthy(row[totalColumn]);

    if (isTotal) {
      // A checkpoint does not move the running total; it shows where it got to.
      bars.push({ label, delta: running, from: 0, to: running, kind: "total" });
    } else {
      const from = running;
      running += value;
      bars.push({ label, delta: value, from, to: running, kind: value < 0 ? "fall" : "rise" });
    }
  });

  if (showTotal && bars.length) {
    bars.push({ label: totalLabel, delta: running, from: 0, to: running, kind: "total" });
  }

  return { bars, skipped };
}

/** The span the value axis has to cover, baseline included. */
export function barsExtent(bars: WaterfallBar[]): { min: number; max: number } {
  if (!bars.length) {
    return { min: 0, max: 0 };
  }
  const levels = bars.flatMap((b) => [b.from, b.to]);
  // Zero is always in range: a waterfall read against a baseline that is not
  // on the chart is not read at all.
  return { min: Math.min(0, ...levels), max: Math.max(0, ...levels) };
}
