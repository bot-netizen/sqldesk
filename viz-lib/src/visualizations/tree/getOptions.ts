import { DEFAULT_VALUE_FORMAT, ValueFormat, normalizeValueFormat } from "../shared/valueOptions";
import { ColumnLike, defaultLabelColumn, defaultValueColumn } from "../shared/rows";

export type TreeLayout = "horizontal" | "vertical" | "radial";

export interface TreeOptions {
  /** The hierarchy, outermost first. Shares its shape with the treemap. */
  pathColumns: string[];
  /** What each leaf is worth. */
  valueColumn: string;
  layout: TreeLayout;
  /** Write the value beside each name. */
  showValues: boolean;
  /** How deep to open it; anything deeper starts folded. */
  initialDepth: number;
  valueFormat: ValueFormat;
}

export const DEFAULT_TREE_OPTIONS = {
  layout: "horizontal" as TreeLayout,
  showValues: false,
  initialDepth: 2,
  valueFormat: DEFAULT_VALUE_FORMAT,
};

/** One to six levels. Anything unreadable as a number means the default. */
export function clampDepth(value: any): number {
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
  return Math.max(1, Math.min(6, asNumber));
}

export default function getOptions(options: any, data?: { columns: ColumnLike[]; rows: any[] }): TreeOptions {
  const o = { ...DEFAULT_TREE_OPTIONS, ...(options || {}) };
  const columns = data ? data.columns : [];
  const rows = data ? data.rows : [];
  const fallback = defaultLabelColumn(columns, rows);

  return {
    ...o,
    pathColumns: Array.isArray(o.pathColumns) && o.pathColumns.length ? o.pathColumns : fallback ? [fallback] : [],
    valueColumn: o.valueColumn || defaultValueColumn(columns, rows),
    layout: (["horizontal", "vertical", "radial"] as TreeLayout[]).includes(o.layout) ? o.layout : "horizontal",
    showValues: !!o.showValues,
    // `|| 2` on its own turns a deliberate 0 into 2, because 0 is falsy --
    // so a depth the caller clamped to the minimum came back as the
    // default instead. Only a value that is not a number should fall back.
    initialDepth: clampDepth(o.initialDepth),
    valueFormat: normalizeValueFormat(o.valueFormat),
  };
}
