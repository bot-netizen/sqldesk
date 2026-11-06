import { DEFAULT_VALUE_FORMAT, ValueFormat, normalizeValueFormat } from "../shared/valueOptions";
import { ColumnLike, defaultValueColumn, numericColumns } from "../shared/rows";

export interface NetworkOptions {
  /** One end of each edge. */
  sourceColumn: string;
  /** The other end. */
  targetColumn: string;
  /** How heavy the edge is. Optional: without one every edge weighs the same. */
  valueColumn: string;
  /** Scale each node by how much flows through it. */
  sizeByWeight: boolean;
  /** Arrowheads, for a graph where direction means something. */
  directed: boolean;
  showLabels: boolean;
  valueFormat: ValueFormat;
}

export const DEFAULT_NETWORK_OPTIONS = {
  sizeByWeight: true,
  directed: false,
  showLabels: true,
  valueFormat: DEFAULT_VALUE_FORMAT,
};

export default function getOptions(options: any, data?: { columns: ColumnLike[]; rows: any[] }): NetworkOptions {
  const o = { ...DEFAULT_NETWORK_OPTIONS, ...(options || {}) };
  const columns = data ? data.columns : [];
  const rows = data ? data.rows : [];

  // The two ends are labels, and they have to be two different columns: the
  // same one twice is a graph of loops, which draws as a pile of dots.
  const numeric = new Set(numericColumns(columns, rows).map((column) => column.name));
  const labels = columns.map((column) => column.name).filter((name) => !numeric.has(name));

  return {
    ...o,
    sourceColumn: o.sourceColumn || labels[0] || "",
    targetColumn: o.targetColumn || labels[1] || "",
    valueColumn: o.valueColumn || defaultValueColumn(columns, rows),
    sizeByWeight: o.sizeByWeight !== false,
    directed: !!o.directed,
    showLabels: o.showLabels !== false,
    valueFormat: normalizeValueFormat(o.valueFormat),
  };
}
