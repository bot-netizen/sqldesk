import { DEFAULT_VALUE_FORMAT, ValueFormat, normalizeValueFormat } from "../shared/valueOptions";
import { defaultValueColumn, ColumnLike } from "../shared/rows";
import { DayRange } from "./days";

export interface CalendarOptions {
  dateColumn: string;
  /** Empty counts the rows landing on each day. */
  valueColumn: string;
  range: DayRange;
  /** The colour the busiest day reaches; quiet days fade towards the track. */
  color: string;
  startOnMonday: boolean;
  valueFormat: ValueFormat;
}

const RANGES: DayRange[] = ["3-months", "12-months", "year", "all"];

/** A date-ish column: what a calendar needs before anything else. */
function defaultDateColumn(columns: ColumnLike[]): string {
  const dated = columns.find((c) => c.type === "date" || c.type === "datetime");
  return dated ? dated.name : columns.length ? columns[0].name : "";
}

export const DEFAULT_CALENDAR_OPTIONS: Omit<CalendarOptions, "dateColumn" | "valueColumn"> = {
  range: "12-months",
  color: "accent",
  startOnMonday: true,
  valueFormat: DEFAULT_VALUE_FORMAT,
};

export default function getOptions(options: any, data?: { columns: ColumnLike[]; rows: any[] }): CalendarOptions {
  const o = { ...DEFAULT_CALENDAR_OPTIONS, ...(options || {}) };
  const columns = data ? data.columns : [];
  const rows = data ? data.rows : [];
  const date = o.dateColumn || defaultDateColumn(columns);
  return {
    ...o,
    dateColumn: date,
    // The value defaults to whatever numeric column is not the date itself;
    // empty means count the rows, which is the other common calendar.
    valueColumn:
      o.valueColumn === undefined
        ? (() => {
            const guess = defaultValueColumn(columns, rows);
            return guess === date ? "" : guess;
          })()
        : o.valueColumn,
    range: RANGES.includes(o.range) ? o.range : "12-months",
    color: typeof o.color === "string" && o.color ? o.color : "accent",
    startOnMonday: !!o.startOnMonday,
    valueFormat: normalizeValueFormat(o.valueFormat),
  };
}
