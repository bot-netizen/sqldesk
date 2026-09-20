import { DEFAULT_VALUE_FORMAT, ValueFormat, normalizeValueFormat } from "../shared/valueOptions";
import { defaultValueColumn, defaultLabelColumn, ColumnLike } from "../shared/rows";

export interface WaterfallOptions {
  labelColumn: string;
  /** Each row's change. A total row's own value is ignored. */
  valueColumn: string;
  /** Rows where this column is true stand from the baseline as a subtotal. */
  totalColumn: string;
  /** Append a final bar for the level everything adds up to. */
  showTotal: boolean;
  totalLabel: string;
  showValues: boolean;
  /** The dotted steps linking one bar's end to the next one's start. */
  showConnectors: boolean;
  riseColor: string;
  fallColor: string;
  totalColor: string;
  valueFormat: ValueFormat;
}

export const DEFAULT_WATERFALL_OPTIONS: Omit<WaterfallOptions, "labelColumn" | "valueColumn"> = {
  totalColumn: "",
  showTotal: true,
  totalLabel: "Total",
  showValues: true,
  showConnectors: true,
  riseColor: "good",
  fallColor: "critical",
  totalColor: "neutral",
  valueFormat: DEFAULT_VALUE_FORMAT,
};

export default function getOptions(options: any, data?: { columns: ColumnLike[]; rows: any[] }): WaterfallOptions {
  const o = { ...DEFAULT_WATERFALL_OPTIONS, ...(options || {}) };
  const columns = data ? data.columns : [];
  const rows = data ? data.rows : [];
  return {
    ...o,
    labelColumn: o.labelColumn === undefined ? defaultLabelColumn(columns, rows) : o.labelColumn,
    valueColumn: o.valueColumn || defaultValueColumn(columns, rows),
    totalColumn: o.totalColumn || "",
    showTotal: !!o.showTotal,
    totalLabel: typeof o.totalLabel === "string" && o.totalLabel ? o.totalLabel : "Total",
    showValues: !!o.showValues,
    showConnectors: !!o.showConnectors,
    valueFormat: normalizeValueFormat(o.valueFormat),
  };
}
