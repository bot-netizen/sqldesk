import { toNumber } from "./valueOptions";

/*
  Helpers for visualizations that read one value, or one value per row, out
  of a result: which row, which column, and whether it holds numbers.
*/

export interface ColumnLike {
  name: string;
  type?: string | null;
}

const NUMERIC_TYPES = ["integer", "float"];

/**
 * The row a "row number" option points at, the way Counter has always read
 * it: 1 is the first row, -1 the last, 0 also the first, and numbers past the
 * end wrap. Returns -1 for an empty result.
 */
export function rowIndex(rowNumber: unknown, rowCount: number): number {
  if (rowCount <= 0) {
    return -1;
  }
  const n = parseInt(String(rowNumber), 10) || 0;
  if (n === 0) {
    return 0;
  }
  const wrapped = (Math.abs(n) - 1) % rowCount;
  return n > 0 ? wrapped : rowCount - wrapped - 1;
}

export function pickRow<T>(rows: T[], rowNumber: unknown): T | null {
  const i = rowIndex(rowNumber, rows.length);
  return i < 0 ? null : rows[i];
}

export function isNumericColumn(column: ColumnLike | undefined, rows: any[] = []): boolean {
  if (!column) {
    return false;
  }
  if (column.type && NUMERIC_TYPES.includes(column.type)) {
    return true;
  }
  // Some drivers report decimals as strings, or report no type at all; look at
  // what came back.
  const sample = rows.slice(0, 20).map((r) => r && r[column.name]);
  const present = sample.filter((v) => v !== null && v !== undefined && v !== "");
  return present.length > 0 && present.every((v) => toNumber(v) !== null);
}

export function numericColumns(columns: ColumnLike[] = [], rows: any[] = []): ColumnLike[] {
  return columns.filter((c) => isNumericColumn(c, rows));
}

/** A sensible default: the first numeric column, else the first column, else "". */
export function defaultValueColumn(columns: ColumnLike[] = [], rows: any[] = []): string {
  const numeric = numericColumns(columns, rows);
  if (numeric.length) {
    return numeric[0].name;
  }
  return columns.length ? columns[0].name : "";
}

/** A sensible default label column: the first column that is not numeric. */
export function defaultLabelColumn(columns: ColumnLike[] = [], rows: any[] = []): string {
  const text = columns.find((c) => !isNumericColumn(c, rows));
  return text ? text.name : "";
}

export function hasColumn(columns: ColumnLike[] = [], name: unknown): boolean {
  return typeof name === "string" && name !== "" && columns.some((c) => c.name === name);
}
