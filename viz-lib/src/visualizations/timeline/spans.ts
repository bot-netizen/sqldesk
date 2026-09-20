import moment from "moment";
import { toNumber } from "../shared/valueOptions";

/*
  Turning rows into bars of state along time.

  Kept apart from the drawing because the time arithmetic is where this goes
  wrong: a span with its ends the wrong way round draws as nothing at all, and
  a run that is still going has no end time to read.
*/

export interface Span {
  /** Which track it sits on. */
  lane: string;
  /** Milliseconds since the epoch. */
  from: number;
  to: number;
  /** What the bar is called and coloured by. Empty when there is no state column. */
  state: string;
  /** The row it came from, for the tooltip. */
  row: any;
  /** True when the row had no end and "now" was used instead. */
  open: boolean;
}

export interface BuiltSpans {
  spans: Span[];
  lanes: string[];
  from: number;
  to: number;
  /** Rows whose start could not be read. */
  undated: number;
}

/** A bar this thin is invisible; every span gets at least this many ms. */
export const MIN_SPAN_MS = 1000;

export function timeOf(value: unknown): number | null {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  if (moment.isMoment(value)) {
    return value.isValid() ? value.valueOf() : null;
  }
  if (value instanceof Date) {
    return isNaN(value.getTime()) ? null : value.getTime();
  }
  // Only strings and numbers go to moment: handed an object it reads whatever
  // fields it recognises and returns a valid date from none of them.
  if (typeof value !== "string" && typeof value !== "number") {
    return null;
  }
  const parsed = moment(value);
  return parsed.isValid() ? parsed.valueOf() : null;
}

export interface BuildSpansInput {
  rows: any[];
  laneColumn: string;
  startColumn: string;
  /** When empty, `durationColumn` is used instead. */
  endColumn: string;
  /** Seconds from the start. Only read when there is no end column. */
  durationColumn: string;
  stateColumn: string;
  /** Stands in for the end of a run that has not finished. */
  now?: number;
}

export default function buildSpans({
  rows,
  laneColumn,
  startColumn,
  endColumn,
  durationColumn,
  stateColumn,
  now = Date.now(),
}: BuildSpansInput): BuiltSpans {
  const spans: Span[] = [];
  const lanes: string[] = [];
  let undated = 0;

  (rows || []).forEach((row) => {
    const start = timeOf(row ? row[startColumn] : null);
    if (start === null) {
      undated += 1;
      return;
    }

    let end: number | null = null;
    let open = false;
    if (endColumn) {
      end = timeOf(row[endColumn]);
    } else if (durationColumn) {
      const seconds = toNumber(row[durationColumn]);
      end = seconds === null || !Number.isFinite(seconds) ? null : start + seconds * 1000;
    }
    if (end === null) {
      // A run with no end is still running. Drawing it up to now says that;
      // dropping it would make a live incident disappear from the timeline.
      end = now;
      open = true;
    }

    // Ends the wrong way round draw as nothing at all, so they are put right
    // rather than silently vanishing.
    const from = Math.min(start, end);
    const to = Math.max(start, end);

    const lane = laneColumn && row[laneColumn] !== undefined && row[laneColumn] !== null ? String(row[laneColumn]) : "";
    if (!lanes.includes(lane)) {
      lanes.push(lane);
    }

    spans.push({
      lane,
      from,
      to: Math.max(to, from + MIN_SPAN_MS),
      state: stateColumn && row[stateColumn] !== undefined && row[stateColumn] !== null ? String(row[stateColumn]) : "",
      row,
      open,
    });
  });

  const starts = spans.map((s) => s.from);
  const ends = spans.map((s) => s.to);
  return {
    spans,
    lanes,
    from: starts.length ? Math.min(...starts) : now,
    to: ends.length ? Math.max(...ends) : now,
    undated,
  };
}
