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

/** One to four levels. Anything unreadable as a number means the default. */
export function clampVisibleDepth(value: any): number {
  // `Number(null)` and `Number("")` are both 0, and both finite -- so an
  // option that is simply absent would clamp to the minimum instead of
  // falling back. Emptiness has to be caught before the coercion.
  if (value === null || value === undefined || value === "") {
    return 2;
  }
  const asNumber = Math.round(Number(value));
  if (!Number.isFinite(asNumber)) {
    return 2;
  }
  return Math.max(1, Math.min(4, asNumber));
}

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
    // `|| 2` turns a deliberate 0 into 2, because 0 is falsy -- so a depth
    // meant to clamp to the minimum came back as the default. Only a value
    // that is not a number should fall back.
    visibleDepth: clampVisibleDepth(o.visibleDepth),
    showBreadcrumb: !!o.showBreadcrumb,
    showValues: !!o.showValues,
    valueFormat: normalizeValueFormat(o.valueFormat),
  };
}
