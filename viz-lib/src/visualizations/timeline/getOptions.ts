import { ValueMapping, normalizeMappings } from "../shared/valueOptions";
import { ColumnLike } from "../shared/rows";
import { DEFAULT_STATUS_MAPPINGS } from "../status-grid/getOptions";

export interface TimelineOptions {
  /** One track per distinct value. Empty puts everything on one track. */
  laneColumn: string;
  startColumn: string;
  /** Where each bar ends. Empty falls back to the duration column. */
  endColumn: string;
  /** Seconds from the start, read only when there is no end column. */
  durationColumn: string;
  /** What each bar is called and coloured by. */
  stateColumn: string;
  /** Used when a state has no mapping and no state column exists. */
  defaultColor: string;
  showLabels: boolean;
  timeFormat: string;
  mappings: ValueMapping[];
}

/** A date-ish column: what a timeline needs before anything else. */
function defaultTimeColumn(columns: ColumnLike[], skip: string[] = []): string {
  const dated = columns.find((c) => (c.type === "date" || c.type === "datetime") && !skip.includes(c.name));
  return dated ? dated.name : "";
}

export const DEFAULT_TIMELINE_OPTIONS: Omit<TimelineOptions, "laneColumn" | "startColumn" | "endColumn"> = {
  durationColumn: "",
  stateColumn: "",
  defaultColor: "accent",
  showLabels: false,
  timeFormat: "D MMM HH:mm",
  // The same words a status grid already knows, so a timeline over a status
  // column colours itself before anyone opens the editor.
  mappings: DEFAULT_STATUS_MAPPINGS,
};

export default function getOptions(options: any, data?: { columns: ColumnLike[]; rows: any[] }): TimelineOptions {
  const o = { ...DEFAULT_TIMELINE_OPTIONS, ...(options || {}) };
  const columns = data ? data.columns : [];
  const start = o.startColumn || defaultTimeColumn(columns);
  return {
    ...o,
    laneColumn:
      o.laneColumn === undefined ? columns.find((c) => !c.type || c.type === "string")?.name ?? "" : o.laneColumn,
    startColumn: start,
    endColumn: o.endColumn === undefined ? defaultTimeColumn(columns, [start]) : o.endColumn,
    durationColumn: o.durationColumn || "",
    stateColumn: o.stateColumn || "",
    defaultColor: typeof o.defaultColor === "string" && o.defaultColor ? o.defaultColor : "accent",
    showLabels: !!o.showLabels,
    timeFormat: typeof o.timeFormat === "string" && o.timeFormat ? o.timeFormat : "D MMM HH:mm",
    mappings: normalizeMappings(o.mappings),
  };
}
