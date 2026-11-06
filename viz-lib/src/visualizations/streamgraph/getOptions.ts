import { DEFAULT_VALUE_FORMAT, ValueFormat, normalizeValueFormat } from "../shared/valueOptions";
import { ColumnLike, defaultLabelColumn, defaultValueColumn } from "../shared/rows";

export interface StreamgraphOptions {
  /** What runs along the axis. Usually a date. */
  xColumn: string;
  /** Which band a row belongs to. */
  seriesColumn: string;
  /** How thick the band is at that point. */
  valueColumn: string;
  showLegend: boolean;
  valueFormat: ValueFormat;
}

export const DEFAULT_STREAMGRAPH_OPTIONS: Omit<StreamgraphOptions, "xColumn" | "seriesColumn" | "valueColumn"> = {
  showLegend: true,
  valueFormat: DEFAULT_VALUE_FORMAT,
};

export default function getOptions(options: any, data?: { columns: ColumnLike[]; rows: any[] }): StreamgraphOptions {
  const o = { ...DEFAULT_STREAMGRAPH_OPTIONS, ...(options || {}) };
  const columns = data ? data.columns : [];
  const rows = data ? data.rows : [];

  // The axis and the band are both labels, so the fallback has to pick two
  // different ones rather than the same column twice -- which would draw a
  // single band and look like the data was wrong.
  const firstLabel = defaultLabelColumn(columns, rows);
  const otherLabel = (columns.find((c) => c.name !== firstLabel && c.name !== o.valueColumn) || { name: "" }).name;

  return {
    ...o,
    xColumn: o.xColumn || firstLabel,
    seriesColumn: o.seriesColumn || otherLabel,
    valueColumn: o.valueColumn || defaultValueColumn(columns, rows),
    showLegend: o.showLegend !== false,
    valueFormat: normalizeValueFormat(o.valueFormat),
  };
}
