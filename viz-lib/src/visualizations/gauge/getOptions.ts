import { DEFAULT_VALUE_FORMAT, ValueFormat, Thresholds, normalizeValueFormat } from "../shared/valueOptions";
import { defaultValueColumn, ColumnLike } from "../shared/rows";

export type GaugeStyle = "needle" | "ring" | "half";

export interface GaugeOptions {
  valueColumn: string;
  /** Which row: 1 is the first, -1 the last (Counter's convention). */
  rowNumber: number;
  style: GaugeStyle;
  /** Text under the value. Empty uses the column name. */
  label: string;
  min: number;
  max: number;
  /** A column holding the minimum or maximum, when it varies by result. */
  minColumn: string;
  maxColumn: string;
  /** A marker on the arc: a constant, or a column. */
  target: number | null;
  targetColumn: string;
  valueFormat: ValueFormat;
  thresholds: Thresholds;
}

export const DEFAULT_GAUGE_OPTIONS: Omit<GaugeOptions, "valueColumn"> = {
  rowNumber: 1,
  style: "needle",
  label: "",
  min: 0,
  max: 100,
  minColumn: "",
  maxColumn: "",
  target: null,
  targetColumn: "",
  valueFormat: DEFAULT_VALUE_FORMAT,
  // Accent until someone sets bands: a gauge with no thresholds is a reading,
  // not a judgement, and should not look "good" by default.
  thresholds: { base: "accent", steps: [] },
};

const STYLES: GaugeStyle[] = ["needle", "ring", "half"];

function finite(value: unknown, fallback: number): number {
  const n = typeof value === "string" && value.trim() === "" ? NaN : Number(value);
  return Number.isFinite(n) ? n : fallback;
}

export default function getOptions(options: any, data?: { columns: ColumnLike[]; rows: any[] }): GaugeOptions {
  const o = { ...DEFAULT_GAUGE_OPTIONS, ...(options || {}) };
  return {
    ...o,
    valueColumn: o.valueColumn || defaultValueColumn(data ? data.columns : [], data ? data.rows : []),
    rowNumber: finite(o.rowNumber, 1),
    style: STYLES.includes(o.style) ? o.style : "needle",
    min: finite(o.min, 0),
    max: finite(o.max, 100),
    target: o.target === null || o.target === undefined || o.target === "" ? null : finite(o.target, NaN),
    valueFormat: normalizeValueFormat(o.valueFormat),
    thresholds: o.thresholds && typeof o.thresholds === "object" ? o.thresholds : DEFAULT_GAUGE_OPTIONS.thresholds,
  };
}
