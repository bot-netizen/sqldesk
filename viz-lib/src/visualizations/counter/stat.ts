import {
  computeDelta,
  formatDelta,
  hasThresholds,
  thresholdColor,
  resolveColor,
  toNumber,
  DeltaMode,
} from "../shared/valueOptions";
import { rowIndex, hasColumn } from "../shared/rows";

/*
  What turns a Counter into a Stat: a sparkline of the value over time, a
  change against something, and threshold colour. All of it is opt-in -- a
  counter saved before these options existed renders exactly as it did.
*/

export type ComparisonMode = "none" | "target" | "previous" | "rowsBack" | "previousRefresh";

export interface SparklineOptions {
  enabled: boolean;
  /** Orders the points. Empty keeps the query's order. */
  timeColumn: string;
}

export interface ComparisonOptions {
  mode: ComparisonMode;
  rowsBack: number;
  display: DeltaMode;
  /** Whether a rise is good news: revenue yes, error rate no. */
  upIsGood: boolean;
}

export const DEFAULT_SPARKLINE: SparklineOptions = { enabled: false, timeColumn: "" };
export const DEFAULT_COMPARISON: ComparisonOptions = { mode: "none", rowsBack: 1, display: "percent", upIsGood: true };

export interface StatExtras {
  /** The rows in the order the counter reads them. */
  rows: any[];
  /** Sparkline points, oldest first, or null when off. */
  spark: number[] | null;
  delta: { text: string; label: string; tone: "good" | "critical" | "neutral" } | null;
  /** A colour for the number from thresholds, or null to keep the classic trend colouring. */
  valueColor: string | null;
}

function timeKey(value: unknown): number {
  if (value === null || value === undefined || value === "") {
    return NaN;
  }
  const n = toNumber(value);
  if (n !== null) {
    return n;
  }
  const t = Date.parse(String(value));
  return Number.isNaN(t) ? NaN : t;
}

/**
 * Rows oldest first by the time column, when the sparkline has one. Rows
 * whose time cannot be read keep their place at the end rather than vanish.
 */
export function orderRows(rows: any[], options: any, columns: { name: string }[] = []): any[] {
  const spark: SparklineOptions = { ...DEFAULT_SPARKLINE, ...(options.sparkline || {}) };
  if (!spark.enabled || !hasColumn(columns, spark.timeColumn)) {
    return rows;
  }
  return rows
    .map((row, i) => ({ row, i, t: timeKey(row && row[spark.timeColumn]) }))
    .sort((a, b) => {
      const at = Number.isNaN(a.t) ? Infinity : a.t;
      const bt = Number.isNaN(b.t) ? Infinity : b.t;
      return at === bt ? a.i - b.i : at - bt;
    })
    .map((x) => x.row);
}

/** The row the headline number comes from: the latest point with a sparkline. */
export function headlineIndex(rows: any[], options: any): number {
  const spark: SparklineOptions = { ...DEFAULT_SPARKLINE, ...(options.sparkline || {}) };
  if (spark.enabled) {
    return rows.length - 1;
  }
  return rowIndex(options.rowNumber, rows.length);
}

const LABELS: Record<Exclude<ComparisonMode, "none">, (n: number) => string> = {
  target: () => "vs target",
  previous: () => "vs previous",
  rowsBack: (n) => `vs ${n} ${n === 1 ? "row" : "rows"} back`,
  previousRefresh: () => "since last refresh",
};

export function getStatExtras(
  orderedRows: any[],
  options: any,
  previousRefreshValue: number | null = null,
  locale?: string
): StatExtras {
  const spark: SparklineOptions = { ...DEFAULT_SPARKLINE, ...(options.sparkline || {}) };
  const comparison: ComparisonOptions = { ...DEFAULT_COMPARISON, ...(options.comparison || {}) };
  const column = options.counterColName;
  const h = headlineIndex(orderedRows, options);
  const current = h >= 0 && !options.countRow ? toNumber(orderedRows[h] && orderedRows[h][column]) : null;
  const currentValue = options.countRow ? orderedRows.length : current;

  const points =
    spark.enabled && !options.countRow
      ? orderedRows.map((r) => toNumber(r && r[column])).filter((v): v is number => v !== null)
      : null;

  let compareTo: number | null = null;
  const n = Math.max(1, Math.round(Number(comparison.rowsBack) || 1));
  switch (comparison.mode) {
    case "target": {
      const t = rowIndex(options.targetRowNumber, orderedRows.length);
      compareTo = t >= 0 && options.targetColName ? toNumber(orderedRows[t][options.targetColName]) : null;
      break;
    }
    case "previous":
      compareTo = h >= 1 ? toNumber(orderedRows[h - 1][column]) : null;
      break;
    case "rowsBack":
      compareTo = h >= n ? toNumber(orderedRows[h - n][column]) : null;
      break;
    case "previousRefresh":
      compareTo = previousRefreshValue;
      break;
    default:
      compareTo = null;
  }

  let delta: StatExtras["delta"] = null;
  if (comparison.mode !== "none") {
    const d = computeDelta(currentValue, compareTo);
    if (d) {
      const format = options.formatMode === "value" ? options.valueFormat : { style: "number" };
      const good = comparison.upIsGood ? d.direction === "up" : d.direction === "down";
      delta = {
        text: formatDelta(d, comparison.display, format, locale),
        label: LABELS[comparison.mode](n),
        tone: d.direction === "flat" ? "neutral" : good ? "good" : "critical",
      };
    }
  }

  // An empty base colour means "leave the number alone below the first step".
  const named =
    hasThresholds(options.thresholds) && currentValue !== null
      ? thresholdColor(currentValue, options.thresholds)
      : null;
  const valueColor = named ? resolveColor(named) : null;

  return { rows: orderedRows, spark: points, delta, valueColor };
}
