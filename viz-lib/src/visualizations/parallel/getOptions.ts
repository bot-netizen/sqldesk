import { DEFAULT_VALUE_FORMAT, ValueFormat, normalizeValueFormat } from "../shared/valueOptions";
import { ColumnLike, numericColumns } from "../shared/rows";

export interface ParallelOptions {
  /** One vertical axis each, left to right in this order. */
  dimensionColumns: string[];
  /** What to colour the lines by. Optional. */
  seriesColumn: string;
  /** Below this many rows every line is drawn solid. */
  showLegend: boolean;
  valueFormat: ValueFormat;
}

export const DEFAULT_PARALLEL_OPTIONS = {
  showLegend: true,
  valueFormat: DEFAULT_VALUE_FORMAT,
};

export default function getOptions(options: any, data?: { columns: ColumnLike[]; rows: any[] }): ParallelOptions {
  const o = { ...DEFAULT_PARALLEL_OPTIONS, ...(options || {}) };
  const columns = data ? data.columns : [];
  const rows = data ? data.rows : [];
  const numbers = numericColumns(columns, rows).map((column) => column.name);

  return {
    ...o,
    // Every numeric column by default. Two is the least that says anything:
    // one axis is a strip chart, and the whole point is what happens
    // *between* axes.
    dimensionColumns: Array.isArray(o.dimensionColumns) && o.dimensionColumns.length ? o.dimensionColumns : numbers,
    seriesColumn: o.seriesColumn || "",
    showLegend: o.showLegend !== false,
    valueFormat: normalizeValueFormat(o.valueFormat),
  };
}
