import { DEFAULT_VALUE_FORMAT, ValueFormat, Thresholds, normalizeValueFormat } from "../shared/valueOptions";
import { defaultValueColumn, defaultLabelColumn, ColumnLike } from "../shared/rows";

export type ProgressMode = "bullet" | "bar";

export interface ProgressOptions {
  /** "bullet": a thin bar over graded bands with a target tick. "bar": a filled track. */
  mode: ProgressMode;
  labelColumn: string;
  valueColumn: string;
  /** Each row's goal, from a column or one constant for all rows. */
  targetColumn: string;
  target: number | null;
  /** The end of the scale when there is no target. Empty uses the largest value. */
  max: number | null;
  valueFormat: ValueFormat;
  /**
   * Against percent of target when there is a target (enter 60 for 60%),
   * against the value itself when there is not.
   */
  thresholds: Thresholds;
}

export const DEFAULT_PROGRESS_OPTIONS: Omit<ProgressOptions, "labelColumn" | "valueColumn"> = {
  mode: "bullet",
  targetColumn: "",
  target: null,
  max: null,
  valueFormat: DEFAULT_VALUE_FORMAT,
  // Behind target is the problem; at or past it is good.
  thresholds: {
    base: "critical",
    steps: [
      { value: 70, color: "warning" },
      { value: 100, color: "good" },
    ],
  },
};

function numberOrNull(v: unknown): number | null {
  if (v === null || v === undefined || v === "") {
    return null;
  }
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

export default function getOptions(options: any, data?: { columns: ColumnLike[]; rows: any[] }): ProgressOptions {
  const o = { ...DEFAULT_PROGRESS_OPTIONS, ...(options || {}) };
  const columns = data ? data.columns : [];
  const rows = data ? data.rows : [];
  return {
    ...o,
    mode: o.mode === "bar" ? "bar" : "bullet",
    labelColumn: o.labelColumn === undefined ? defaultLabelColumn(columns, rows) : o.labelColumn,
    valueColumn: o.valueColumn || defaultValueColumn(columns, rows),
    target: numberOrNull(o.target),
    max: numberOrNull(o.max),
    valueFormat: normalizeValueFormat(o.valueFormat),
    thresholds: o.thresholds && typeof o.thresholds === "object" ? o.thresholds : DEFAULT_PROGRESS_OPTIONS.thresholds,
  };
}
