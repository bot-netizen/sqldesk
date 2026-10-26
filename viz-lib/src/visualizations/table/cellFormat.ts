import type React from "react";
import {
  Thresholds,
  ValueMapping,
  thresholdColor,
  findMapping,
  resolveColor,
  washColor,
  toNumber,
  isSemanticColor,
  SEMANTIC_COLORS,
} from "../shared/valueOptions";

/*
  Conditional formatting for table cells: colour by rules or by a scale, a
  data bar behind a number, and a mark on cells whose value changed since the
  last refresh. Stored per column as `cellFormat`, absent on every column
  saved before 0.4 -- which therefore renders exactly as it did.
*/

export type CellColorMode = "none" | "rules" | "scale";

export interface CellFormat {
  color: CellColorMode;
  /** Colour the cell behind the text, or the text itself. */
  colorTarget: "background" | "text";
  /** For numbers. The base colour may be empty: no colour below the first step. */
  rules: Thresholds;
  /** For text: exact values to colours. */
  mappings: ValueMapping[];
  /** The one colour a scale deepens from the column's minimum to its maximum. */
  scaleColor: string;
  dataBar: boolean;
  /** The bar's colour, and the colour it takes below zero. */
  dataBarColor: string;
  dataBarNegativeColor: string;
  showChange: boolean;
}

export const DEFAULT_CELL_FORMAT: CellFormat = {
  color: "none",
  colorTarget: "background",
  rules: { base: "", steps: [] },
  mappings: [],
  scaleColor: "accent",
  dataBar: false,
  // The colours the bar has always been drawn in, named rather than assumed,
  // so a column saved before this renders exactly as it did.
  dataBarColor: "accent",
  dataBarNegativeColor: "danger",
  showChange: false,
};

export function normalizeCellFormat(format: Partial<CellFormat> | null | undefined): CellFormat {
  const f = { ...DEFAULT_CELL_FORMAT, ...(format || {}) };
  return {
    ...f,
    color: ["none", "rules", "scale"].includes(f.color) ? f.color : "none",
    colorTarget: f.colorTarget === "text" ? "text" : "background",
    rules: f.rules && typeof f.rules === "object" ? f.rules : DEFAULT_CELL_FORMAT.rules,
    mappings: Array.isArray(f.mappings) ? f.mappings : [],
  };
}

export function isFormatted(format: Partial<CellFormat> | null | undefined): boolean {
  const f = normalizeCellFormat(format);
  return f.color !== "none" || f.dataBar || f.showChange;
}

export interface ColumnStats {
  min: number;
  max: number;
}

/** Min and max of a column's numbers, or null if it has none. */
export function columnStats(rows: any[], column: string): ColumnStats | null {
  let min = Infinity;
  let max = -Infinity;
  for (const row of rows) {
    const n = toNumber(row && row[column]);
    if (n !== null) {
      min = Math.min(min, n);
      max = Math.max(max, n);
    }
  }
  return min === Infinity ? null : { min, max };
}

/** A colour name for this cell, from rules (numbers) or mappings (text). */
function ruleColor(value: unknown, f: CellFormat): string | null {
  const mapped = findMapping(value, f.mappings);
  if (mapped && mapped.color) {
    return mapped.color;
  }
  const c = thresholdColor(value, f.rules);
  return c || null;
}

function mix(color: string, percent: number) {
  return `color-mix(in srgb, ${resolveColor(color)} ${Math.round(percent)}%, transparent)`;
}

export function cellStyle(
  value: unknown,
  format: Partial<CellFormat> | null | undefined,
  stats: ColumnStats | null
): React.CSSProperties | undefined {
  const f = normalizeCellFormat(format);
  if (f.color === "rules") {
    const c = ruleColor(value, f);
    if (!c) {
      return undefined;
    }
    return f.colorTarget === "text"
      ? { color: resolveColor(c), fontWeight: 600 }
      : { background: washColor(c), color: isSemanticColor(c) ? resolveColor(c) : undefined };
  }
  if (f.color === "scale") {
    const n = toNumber(value);
    if (n === null || !stats) {
      return undefined;
    }
    const t = stats.max > stats.min ? (n - stats.min) / (stats.max - stats.min) : 1;
    if (f.colorTarget === "text") {
      return { color: resolveColor(f.scaleColor), opacity: 0.45 + 0.55 * t };
    }
    // 6% at the minimum to 46% at the maximum: light enough that text stays
    // readable on the deepest cell.
    return { background: mix(f.scaleColor, 6 + 40 * t) };
  }
  return undefined;
}

export interface DataBar {
  /** Percent across the cell where the bar starts. */
  offset: number;
  /** Percent of the cell the bar covers. */
  width: number;
  /** Which of the two colours it takes. */
  negative: boolean;
}

/**
 * Where a data bar sits in its cell, and which way it points.
 *
 * The bar used to be the magnitude alone, always growing from the left edge,
 * so -90 and 90 drew the same bar. On a column of variances that is the one
 * thing the reader needs and the only thing the bar did not say.
 *
 * Three cases, because a shared zero is worth the width it costs only when
 * there is something on both sides of it:
 *
 *   all values >= 0   left edge to the right, the full cell for the range
 *   all values <= 0   right edge to the left, the mirror of it
 *   values of both    zero in the middle, and the sign is the direction
 */
export function dataBarGeometry(value: unknown, stats: ColumnStats | null): DataBar | null {
  const n = toNumber(value);
  if (n === null || !stats) {
    return null;
  }
  const extent = Math.max(Math.abs(stats.min), Math.abs(stats.max));
  if (extent === 0) {
    // Every value is zero. No bar, but not "no number here" either.
    return { offset: 0, width: 0, negative: false };
  }
  const share = (Math.abs(n) / extent) * 100;

  if (stats.min >= 0) {
    return { offset: 0, width: share, negative: false };
  }
  if (stats.max <= 0) {
    return { offset: 100 - share, width: share, negative: true };
  }
  const half = share / 2;
  return n < 0 ? { offset: 50 - half, width: half, negative: true } : { offset: 50, width: half, negative: false };
}

/** Whether a column needs the zero line drawn, which is where it has two sides. */
export function dataBarIsSigned(stats: ColumnStats | null): boolean {
  return !!stats && stats.min < 0 && stats.max > 0;
}

export type Change = "up" | "down" | "changed";

export function changeBetween(previous: unknown, current: unknown): Change | null {
  if (previous === undefined) {
    return null; // a row we had not seen: nothing to compare
  }
  const p = toNumber(previous);
  const c = toNumber(current);
  if (p !== null && c !== null) {
    return c > p ? "up" : c < p ? "down" : null;
  }
  return String(previous ?? "") === String(current ?? "") ? null : "changed";
}

/**
 * How rows are matched between refreshes: by the first column when its
 * values are unique (an id, a name), otherwise by position.
 */
export function rowIdentity(columns: { name: string }[], rows: any[]): (record: any, index: number) => string {
  const first = columns && columns[0] ? columns[0].name : null;
  if (first) {
    const seen = new Set<string>();
    let unique = true;
    for (const r of rows) {
      const k = String(r && r[first]);
      if (seen.has(k)) {
        unique = false;
        break;
      }
      seen.add(k);
    }
    if (unique) {
      return (record) => `k:${String(record && record[first])}`;
    }
  }
  return (_record, index) => `i:${index}`;
}

export const SCALE_COLORS = Object.keys(SEMANTIC_COLORS);
