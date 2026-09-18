import {
  DEFAULT_VALUE_FORMAT,
  ValueFormat,
  Thresholds,
  ValueMapping,
  normalizeValueFormat,
} from "../shared/valueOptions";
import { defaultValueColumn, defaultLabelColumn, ColumnLike, isNumericColumn } from "../shared/rows";

export type TileSize = "small" | "medium" | "large";
export type TileSort = "none" | "severity" | "name";

export interface StatusGridOptions {
  nameColumn: string;
  /** The number shown on each tile, and what thresholds colour by. */
  valueColumn: string;
  /** Status text ("ok", "degraded") that mappings colour by; wins over thresholds. */
  statusColumn: string;
  /** A small line under the value. */
  detailColumn: string;
  tileSize: TileSize;
  sort: TileSort;
  valueFormat: ValueFormat;
  thresholds: Thresholds;
  mappings: ValueMapping[];
}

// Words status columns actually contain, so a grid over one colours itself
// before anyone opens the editor.
export const DEFAULT_STATUS_MAPPINGS: ValueMapping[] = [
  ...["ok", "up", "healthy", "pass", "passing", "success", "green"].map((value) => ({
    value,
    text: "",
    color: "good",
  })),
  ...["warning", "warn", "degraded", "slow", "pending", "amber", "yellow"].map((value) => ({
    value,
    text: "",
    color: "warning",
  })),
  ...["critical", "down", "error", "failed", "fail", "failing", "outage", "red"].map((value) => ({
    value,
    text: "",
    color: "critical",
  })),
];

export const DEFAULT_STATUS_GRID_OPTIONS = {
  statusColumn: "",
  detailColumn: "",
  tileSize: "medium" as TileSize,
  sort: "none" as TileSort,
  valueFormat: DEFAULT_VALUE_FORMAT,
  thresholds: { base: "good", steps: [] } as Thresholds,
};

const SIZES: TileSize[] = ["small", "medium", "large"];
const SORTS: TileSort[] = ["none", "severity", "name"];

export default function getOptions(options: any, data?: { columns: ColumnLike[]; rows: any[] }): StatusGridOptions {
  const o = { ...DEFAULT_STATUS_GRID_OPTIONS, ...(options || {}) };
  const columns = data ? data.columns : [];
  const rows = data ? data.rows : [];
  const numeric = columns.find((c) => isNumericColumn(c, rows));
  return {
    ...o,
    nameColumn: o.nameColumn === undefined ? defaultLabelColumn(columns, rows) : o.nameColumn,
    // A status-only result has no number to show; do not invent one.
    valueColumn: o.valueColumn === undefined ? (numeric ? defaultValueColumn(columns, rows) : "") : o.valueColumn,
    tileSize: SIZES.includes(o.tileSize) ? o.tileSize : "medium",
    sort: SORTS.includes(o.sort) ? o.sort : "none",
    valueFormat: normalizeValueFormat(o.valueFormat),
    thresholds:
      o.thresholds && typeof o.thresholds === "object" ? o.thresholds : DEFAULT_STATUS_GRID_OPTIONS.thresholds,
    mappings: Array.isArray(o.mappings) ? o.mappings : DEFAULT_STATUS_MAPPINGS,
  };
}
