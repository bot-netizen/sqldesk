import { DEFAULT_VALUE_FORMAT, ValueFormat, Thresholds, normalizeValueFormat } from "../shared/valueOptions";
import { defaultValueColumn, ColumnLike } from "../shared/rows";

export type GaugeStyle = "reading" | "needle" | "ring" | "half";

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
  /**
   * Orders the trail the reading style draws behind its number. Empty keeps
   * the query's order; set, the reading is the newest point rather than the
   * one `rowNumber` picks.
   */
  trailColumn: string;
  valueFormat: ValueFormat;
  thresholds: Thresholds;
}

export const DEFAULT_GAUGE_OPTIONS: Omit<GaugeOptions, "valueColumn"> = {
  rowNumber: 1,
  // What a gauge saved before the reading tile existed gets. A new one opens
  // on "reading" -- see `getOptions`.
  style: "needle",
  label: "",
  min: 0,
  max: 100,
  minColumn: "",
  maxColumn: "",
  target: null,
  targetColumn: "",
  trailColumn: "",
  valueFormat: DEFAULT_VALUE_FORMAT,
  // Accent until someone sets bands: a gauge with no thresholds is a reading,
  // not a judgement, and should not look "good" by default.
  thresholds: { base: "accent", steps: [] },
};

const STYLES: GaugeStyle[] = ["reading", "needle", "ring", "half"];

function finite(value: unknown, fallback: number): number {
  const n = typeof value === "string" && value.trim() === "" ? NaN : Number(value);
  return Number.isFinite(n) ? n : fallback;
}

export default function getOptions(options: any, data?: { columns: ColumnLike[]; rows: any[] }): GaugeOptions {
  const saved = options || {};
  // A gauge being created starts from `{}`. It opens on the reading tile --
  // the number, its trail and its range, which is what most gauges are for --
  // while one saved without an explicit style keeps the needle it was drawn
  // with. Same trick as `counter/index.ts`: what tells the two apart is that
  // a new one has no options at all yet.
  const isNew = Object.keys(saved).length === 0;
  const o = { ...DEFAULT_GAUGE_OPTIONS, ...saved };
  return {
    ...o,
    valueColumn: o.valueColumn || defaultValueColumn(data ? data.columns : [], data ? data.rows : []),
    rowNumber: finite(o.rowNumber, 1),
    // `saved.style`, not `o.style`: the latter has already picked up the
    // default below, so it is never absent and the fallback never fires.
    style: STYLES.includes(saved.style) ? saved.style : isNew ? "reading" : "needle",
    min: finite(o.min, 0),
    max: finite(o.max, 100),
    target: o.target === null || o.target === undefined || o.target === "" ? null : finite(o.target, NaN),
    valueFormat: normalizeValueFormat(o.valueFormat),
    thresholds: o.thresholds && typeof o.thresholds === "object" ? o.thresholds : DEFAULT_GAUGE_OPTIONS.thresholds,
  };
}
