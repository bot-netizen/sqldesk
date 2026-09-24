import moment from "moment";
import { parseTimestamp } from "./parseTimestamp";

/*
  This replaced two moment parses per cell with one hand-rolled one, so what
  has to be shown is that it reads every string the same way moment did --
  including the ones it should refuse.
*/

/** What `query-result.js` used to do, kept here as the thing to agree with. */
function asMomentDid(value) {
  if (typeof value !== "string") {
    return null;
  }
  if (/^\d{4}-\d{2}-\d{2}T/.test(value) && moment(value, moment.ISO_8601, true).isValid()) {
    return { ms: moment.utc(value).valueOf(), type: "datetime" };
  }
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return { ms: moment.utc(value).valueOf(), type: "date" };
  }
  return null;
}

const STRINGS = [
  // Timestamps the API actually sends.
  "2022-01-01T00:00:00",
  "2022-01-01T12:34:56.789",
  "2024-02-29T00:00:00",
  "2021-01-27",
  // Zones, in all the ways they are written.
  "2022-01-01T00:00:00Z",
  "2022-01-01T00:00:00+09:00",
  "2022-01-01T00:00:00-0530",
  "2022-12-31T23:59:59.999-08:00",
  // Legal ISO oddities.
  "2022-01-01T24:00:00",
  "2022-01-01T00:00",
  "2022-01-01T00:00:00,123",
  "2022-01-01T12:34:56.789012Z",
  // Not timestamps, and must stay strings.
  "2022-13-45T00:00:00",
  "2022-02-30T00:00:00",
  "2022-02-29T00:00:00",
  "2021-01-27T00:00:01.733983944+03:00 stderr F {",
  "2021-01-27Z00:00:00+09:00",
  "2022-1-1T00:00:00",
  "2022-01-01 00:00:00",
  "2022-06-15T23:59:60Z",
  "foo bar",
  "",
  "acme-corp",
];

describe("reading a timestamp out of a cell", () => {
  test.each(STRINGS)("%p is read exactly as moment read it", (value) => {
    expect(parseTimestamp(value)).toEqual(asMomentDid(value));
  });

  test.each([[2022], [null], [undefined], [true], [{}], [[]], [new Date()]])("%p is not a timestamp", (value) => {
    expect(parseTimestamp(value)).toBeNull();
  });

  test("a date with no time in it is midnight UTC, not midnight here", () => {
    // Read locally, a day in a negative-offset zone becomes the previous
    // evening and the whole column shifts by a day.
    expect(parseTimestamp("2024-03-05").ms).toBe(Date.UTC(2024, 2, 5));
  });

  test("a date-time with no zone is UTC, which is what the API means", () => {
    expect(parseTimestamp("2024-03-05T09:00:00").ms).toBe(Date.UTC(2024, 2, 5, 9));
  });

  test("a day that does not exist stays a string", () => {
    // V8's own `Date.parse` reads this as the 2nd of March, via the lenient
    // parser it falls back to for anything that is not exactly ISO 8601.
    expect(parseTimestamp("2022-02-30T00:00:00")).toBeNull();
    expect(Date.parse("2022-02-30T00:00:00")).not.toBeNaN();
  });

  test("a date and a date-time are told apart", () => {
    expect(parseTimestamp("2024-03-05").type).toBe("date");
    expect(parseTimestamp("2024-03-05T00:00:00").type).toBe("datetime");
  });

  test("every minute of a year round-trips", () => {
    // A fuzz pass, because the cases above are the ones somebody thought of.
    for (let i = 0; i < 2000; i += 1) {
      const at = new Date(Date.UTC(2024, 0, 1) + i * 262979);
      const iso = at.toISOString();
      expect(parseTimestamp(iso).ms).toBe(at.getTime());
      expect(parseTimestamp(iso.replace("Z", "")).ms).toBe(at.getTime());
    }
  });
});
