import moment from "moment";
import { toNumber } from "../shared/valueOptions";

/*
  Turning rows into one number per day, and working out which days to show.

  Kept apart from the drawing because dates are where this goes wrong: a row
  landing on the day before its own because of a timezone, or two rows for one
  day silently becoming one, are both invisible on a finished calendar.
*/

export type DayRange = "3-months" | "12-months" | "year" | "all";

export interface Day {
  /** YYYY-MM-DD, which is what ECharts' calendar wants. */
  date: string;
  value: number;
}

export interface BuiltDays {
  days: Day[];
  /** The span to draw, inclusive, as YYYY-MM-DD. */
  from: string;
  to: string;
  /** Rows whose date could not be read. */
  undated: number;
  /** Rows whose value was not a number. */
  skipped: number;
  /** Days inside the range that no row landed on. */
  empty: number;
}

export const DAY = "YYYY-MM-DD";

/**
 * The calendar day a value belongs to.
 *
 * Parsed in local time, because that is the day the reader means. A timestamp
 * read as UTC lands on the previous day for anyone west of Greenwich for a
 * good part of every day, which shifts a whole calendar by one square.
 */
export function dayOf(value: unknown): string | null {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  if (moment.isMoment(value)) {
    return value.isValid() ? value.format(DAY) : null;
  }
  if (value instanceof Date) {
    return isNaN(value.getTime()) ? null : moment(value).format(DAY);
  }
  // A plain "2024-03-05" is a day already, and must not be dragged through a
  // timezone on the way in.
  if (typeof value === "string") {
    const bare = value.trim().slice(0, 10);
    if (/^\d{4}-\d{2}-\d{2}$/.test(bare)) {
      return moment(bare, DAY, true).isValid() ? bare : null;
    }
  }
  // Only strings and numbers go to moment. Handed an object it reads the
  // fields it recognises and returns a valid date from none of them -- `{}`
  // comes back as the start of the century, which would put a square on the
  // calendar for a row that has no date at all.
  if (typeof value !== "string" && typeof value !== "number") {
    return null;
  }
  // A string with no digit in it cannot be a date, and handing it to moment
  // means a deprecation warning per row on the console -- which is what
  // pointing a date column at a text column used to produce, hundreds of
  // times over.
  if (typeof value === "string" && !/\d/.test(value)) {
    return null;
  }
  const parsed = moment(value);
  return parsed.isValid() ? parsed.format(DAY) : null;
}

/** The span to draw, given what the data covers and what was asked for. */
export function rangeFor(dates: string[], range: DayRange): { from: string; to: string } {
  if (!dates.length) {
    const today = moment().format(DAY);
    return { from: moment().subtract(11, "months").startOf("month").format(DAY), to: today };
  }
  const sorted = [...dates].sort();
  const first = sorted[0];
  const last = sorted[sorted.length - 1];

  // Every range ends at the newest day in the data rather than at today: a
  // query for last quarter should not draw three empty months up to now.
  switch (range) {
    case "3-months":
      return { from: moment(last, DAY).subtract(2, "months").startOf("month").format(DAY), to: last };
    case "12-months":
      return { from: moment(last, DAY).subtract(11, "months").startOf("month").format(DAY), to: last };
    case "year":
      return {
        from: moment(last, DAY).startOf("year").format(DAY),
        to: moment(last, DAY).endOf("year").format(DAY),
      };
    default:
      return { from: first, to: last };
  }
}

/** The calendar years a span touches, so each gets a row of its own. */
export function yearsIn(from: string, to: string): number[] {
  const firstYear = moment(from, DAY).year();
  const lastYear = moment(to, DAY).year();
  const years: number[] = [];
  for (let year = firstYear; year <= lastYear; year += 1) {
    years.push(year);
  }
  return years;
}

/**
 * One value per day, adding up the rows that land on the same one.
 *
 * Adding rather than replacing: a query returning one row per event is the
 * ordinary case -- commits, orders, incidents -- and taking the last of them
 * would draw a calendar of ones.
 */
export default function buildDays(rows: any[], dateColumn: string, valueColumn: string, range: DayRange): BuiltDays {
  const totals = new Map<string, number>();
  let undated = 0;
  let skipped = 0;

  (rows || []).forEach((row) => {
    const date = dayOf(row ? row[dateColumn] : null);
    if (date === null) {
      undated += 1;
      return;
    }
    // No value column means "count the rows", which is what a calendar of
    // events is for.
    const value = valueColumn ? toNumber(row[valueColumn]) : 1;
    if (value === null || !Number.isFinite(value)) {
      skipped += 1;
      return;
    }
    totals.set(date, (totals.get(date) || 0) + value);
  });

  const { from, to } = rangeFor([...totals.keys()], range);
  const days = [...totals.entries()]
    .filter(([date]) => date >= from && date <= to)
    .map(([date, value]) => ({ date, value }))
    .sort((a, b) => a.date.localeCompare(b.date));

  const spanDays = moment(to, DAY).diff(moment(from, DAY), "days") + 1;
  return { days, from, to, undated, skipped, empty: Math.max(0, spanDays - days.length) };
}
