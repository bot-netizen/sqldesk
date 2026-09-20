import { DEFAULT_VALUE_FORMAT, ValueFormat, normalizeValueFormat } from "../shared/valueOptions";
import { defaultValueColumn, defaultLabelColumn, ColumnLike } from "../shared/rows";

export interface TreemapOptions {
  /** The hierarchy, outermost first. One column is a flat treemap. */
  pathColumns: string[];
  /** What decides each rectangle's area. */
  valueColumn: string;
  /** How many levels to show at once; deeper ones open on click. */
  visibleDepth: number;
  showBreadcrumb: boolean;
  /** Write the value under each name. */
  showValues: boolean;
  valueFormat: ValueFormat;
}

export const DEFAULT_TREEMAP_OPTIONS: Omit<TreemapOptions, "pathColumns" | "valueColumn"> = {
  visibleDepth: 2,
  showBreadcrumb: true,
  showValues: false,
  valueFormat: DEFAULT_VALUE_FORMAT,
};

export default function getOptions(options: any, data?: { columns: ColumnLike[]; rows: any[] }): TreemapOptions {
  const o = { ...DEFAULT_TREEMAP_OPTIONS, ...(options || {}) };
  const columns = data ? data.columns : [];
  const rows = data ? data.rows : [];
  const fallbackPath = defaultLabelColumn(columns, rows);
  return {
    ...o,
    pathColumns:
      Array.isArray(o.pathColumns) && o.pathColumns.length ? o.pathColumns : fallbackPath ? [fallbackPath] : [],
    valueColumn: o.valueColumn || defaultValueColumn(columns, rows),
    visibleDepth: Math.max(1, Math.min(4, Math.round(Number(o.visibleDepth)) || 2)),
    showBreadcrumb: !!o.showBreadcrumb,
    showValues: !!o.showValues,
    valueFormat: normalizeValueFormat(o.valueFormat),
  };
}
