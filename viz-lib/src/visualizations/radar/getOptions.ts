import { DEFAULT_VALUE_FORMAT, ValueFormat, normalizeValueFormat } from "../shared/valueOptions";
import { defaultLabelColumn, numericColumns, ColumnLike } from "../shared/rows";
import { ScaleMode } from "./spokes";

export interface RadarOptions {
  /** Names each shape on the web. Empty numbers the rows. */
  labelColumn: string;
  /** One spoke per column, in this order. */
  valueColumns: string[];
  /** Per-spoke scales let measures in different units share a chart. */
  scaleMode: ScaleMode;
  shape: "polygon" | "circle";
  showArea: boolean;
  showLegend: boolean;
  valueFormat: ValueFormat;
}

/** More shapes than this and the web is a smudge, whatever the colours. */
export const MAX_SHAPES = 12;

export const DEFAULT_RADAR_OPTIONS: Omit<RadarOptions, "labelColumn" | "valueColumns"> = {
  scaleMode: "per-spoke",
  shape: "polygon",
  showArea: true,
  showLegend: true,
  valueFormat: DEFAULT_VALUE_FORMAT,
};

export default function getOptions(options: any, data?: { columns: ColumnLike[]; rows: any[] }): RadarOptions {
  const o = { ...DEFAULT_RADAR_OPTIONS, ...(options || {}) };
  const columns = data ? data.columns : [];
  const rows = data ? data.rows : [];
  // A radar needs at least three spokes to be a radar; a new one takes as many
  // numeric columns as it finds, which is usually the whole point of the query.
  const numeric = numericColumns(columns, rows).map((c) => c.name);
  return {
    ...o,
    labelColumn: o.labelColumn === undefined ? defaultLabelColumn(columns, rows) : o.labelColumn,
    valueColumns: Array.isArray(o.valueColumns) && o.valueColumns.length ? o.valueColumns : numeric,
    scaleMode: o.scaleMode === "shared" ? "shared" : "per-spoke",
    shape: o.shape === "circle" ? "circle" : "polygon",
    showArea: !!o.showArea,
    showLegend: !!o.showLegend,
    valueFormat: normalizeValueFormat(o.valueFormat),
  };
}
