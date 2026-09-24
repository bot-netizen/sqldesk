/*
  Reading the timestamps out of a query result.

  This runs on every cell of every result, and on a big one it was the single
  most expensive thing about taking a result in. Measured on 20,000 ISO
  date-time strings (Node 24, same V8 as the browser):

    isDateTime + moment.utc(string)     253 ms
    this                                 20 ms

  Most of that was not moment being slow. It was moment being asked twice:
  `isDateTime` did a strict `moment(v, ISO_8601, true)` parse purely to decide
  whether the cell *was* a timestamp, threw the answer away, and then
  `moment.utc(v)` parsed the identical string again. One parse, done here by
  hand, removes both.

  The moments themselves are kept. Of the 20ms left, 10.6 is this parse and
  9.1 is building the moment objects -- so dropping them for plain `Date`s
  would save another 3.6% of the original, at the price of changing eleven
  consumers across two packages, each of which asks `moment.isMoment` and
  would silently start formatting a Date as `String(value)`. Not a trade
  worth making.

  Hand-rolled rather than `Date.parse`, because V8 falls back to a lenient
  legacy parser when a string is not exactly ISO 8601, and that parser reads
  "2022-02-30T00:00:00" as the 2nd of March. A date that does not exist has
  to stay a string, the way it does today -- so the calendar fields are
  checked against the Date they produce.
*/

const DATE_ONLY = /^(\d{4})-(\d{2})-(\d{2})$/;
const DATE_TIME = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2})(?:[.,](\d{1,9}))?)?(Z|[+-]\d{2}:?\d{2})?$/;

/** Midnight UTC on that calendar day, or NaN if there is no such day. */
function utcDay(year, month, day) {
  if (month < 1 || month > 12 || day < 1 || day > 31) {
    return NaN;
  }
  const ms = Date.UTC(year, month - 1, day);
  const at = new Date(ms);
  // Date.UTC rolls February 30th forward into March; a result cell saying
  // that is not a date at all.
  return at.getUTCFullYear() === year && at.getUTCMonth() === month - 1 && at.getUTCDate() === day ? ms : NaN;
}

function zoneOffsetMs(zone) {
  if (!zone || zone === "Z") {
    return 0;
  }
  const sign = zone[0] === "-" ? -1 : 1;
  const [hours, minutes] = zone.slice(1).replace(":", "").match(/\d{2}/g).map(Number);
  return sign * (hours * 3600000 + minutes * 60000);
}

/**
 * Epoch milliseconds and which kind of timestamp it is, or null.
 *
 * "date" is a bare `2024-03-05` -- a day, with no time in it, which is read
 * as midnight UTC so that it does not drift across a timezone. "datetime" is
 * an ISO date-time, with or without a zone; without one it is read as UTC,
 * which is what the API sends and what moment did with it before.
 *
 * @param {unknown} value
 * @returns {{ms: number, type: "date" | "datetime"} | null}
 */
export function parseTimestamp(value) {
  if (typeof value !== "string") {
    return null;
  }

  const dateOnly = DATE_ONLY.exec(value);
  if (dateOnly) {
    const ms = utcDay(+dateOnly[1], +dateOnly[2], +dateOnly[3]);
    return Number.isNaN(ms) ? null : { ms, type: "date" };
  }

  const parts = DATE_TIME.exec(value);
  if (!parts) {
    return null;
  }
  const day = utcDay(+parts[1], +parts[2], +parts[3]);
  if (Number.isNaN(day)) {
    return null;
  }
  const hours = +parts[4];
  const minutes = +parts[5];
  const seconds = parts[6] ? +parts[6] : 0;
  // 24:00 is a legal way to write the end of a day and rolls into the next.
  // A leap second does not parse, because it did not before either.
  if (hours > 24 || minutes > 59 || seconds > 59) {
    return null;
  }
  const fraction = parts[7] ? Math.round(Number(`0.${parts[7]}`) * 1000) : 0;

  return {
    ms: day + hours * 3600000 + minutes * 60000 + seconds * 1000 + fraction - zoneOffsetMs(parts[8]),
    type: "datetime",
  };
}
