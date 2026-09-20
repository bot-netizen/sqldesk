import { DEFAULT_VALUE_FORMAT, ValueFormat, normalizeValueFormat } from "../shared/valueOptions";
import { defaultValueColumn, ColumnLike } from "../shared/rows";
import { clampBinCount } from "./binning";

export interface HistogramOptions {
  /** The numeric column being binned. */
  valueColumn: string;
  /** Null lets the data choose; a number fixes it. */
  binCount: number | null;
  /** Bars as counts, or as a share of the whole. */
  countMode: "count" | "percent";
  /** How a bin's range is written, on the axis and in the tooltip. */
  valueFormat: ValueFormat;
  /** Named colour from the palette, or a literal one. */
  color: string;
  /** Show the mean as a line across the bars. */
  showMean: boolean;
}

export const DEFAULT_HISTOGRAM_OPTIONS: Omit<HistogramOptions, "valueColumn"> = {
  binCount: null,
  countMode: "count",
  valueFormat: DEFAULT_VALUE_FORMAT,
  color: "accent",
  showMean: false,
};

export default function getOptions(options: any, data?: { columns: ColumnLike[]; rows: any[] }): HistogramOptions {
  const o = { ...DEFAULT_HISTOGRAM_OPTIONS, ...(options || {}) };
  const columns = data ? data.columns : [];
  const rows = data ? data.rows : [];
  return {
    ...o,
    valueColumn: o.valueColumn || defaultValueColumn(columns, rows),
    // Anything unusable means "let the data choose", which is the default a
    // new histogram starts from.
    binCount: o.binCount === null || o.binCount === undefined || o.binCount === "" ? null : clampBinCount(o.binCount),
    countMode: o.countMode === "percent" ? "percent" : "count",
    valueFormat: normalizeValueFormat(o.valueFormat),
    color: typeof o.color === "string" && o.color ? o.color : "accent",
    showMean: !!o.showMean,
  };
}
