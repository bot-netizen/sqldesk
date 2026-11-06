import moment from "moment";
import getOptions from "../getOptions";
import buildOption from "./buildOption";
import { timeAxisFormatter, timePointerFormatter, timeSpan } from "./utils";

function series(name: string, points: [any, any][]) {
  return { name, type: "line", data: points.map(([x, y]) => ({ x, y, $raw: { x, y } })) };
}

function options(overrides: any = {}) {
  return getOptions({ globalSeriesType: "line", sortX: false, ...overrides });
}

/*
  How a timestamp reads on a chart.

  Two faults behind this, and the second is the one nobody would have
  reported as a bug.

  ECharts labels a run of days as bare numbers -- "15", "22", "29" -- with
  the month only where it turns, so three months of daily data is a row of
  numbers you have to count back through to read. Within a day it is the
  dates that go missing instead.

  And underneath that: `normalizeX` parses every x with `moment.utc`, while
  ECharts renders in the viewer's own zone unless told otherwise. A daily
  bucket stored as midnight UTC was drawn as 20:00 the day before in
  Toronto. Not a formatting problem -- the wrong day, on every bar.
*/
const DAY = 86400000;
const at = (iso: string) => moment.utc(iso);

function axisOf(points: [any, number][], extra: any = {}) {
  const line = { ...series("v", points), type: "line" };
  return buildOption(
    [line],
    options({ globalSeriesType: "line", xAxis: { type: "-", labels: { enabled: true } }, ...extra })
  ).option;
}

describe("reading the time off a chart", () => {
  test("the chart is drawn in the zone its values were parsed in", () => {
    const built = axisOf([
      [at("2026-09-24T00:00:00Z"), 1],
      [at("2026-09-25T00:00:00Z"), 2],
    ]);

    expect(built.useUTC).toBe(true);
  });

  describe("the axis labels", () => {
    test("a run of days says which month each one is in", () => {
      const label = timeAxisFormatter(30 * DAY);

      expect(label(Date.parse("2026-09-24T00:00:00Z"))).toBe("24 Sep");
      expect(label(Date.parse("2026-10-01T00:00:00Z"))).toBe("1 Oct");
    });

    test("a daily bucket is the day it was stored as, not the evening before", () => {
      const label = timeAxisFormatter(30 * DAY);

      // The whole bug, in one assertion: midnight UTC on the 25th is the
      // 25th, wherever the person reading it happens to be sitting.
      expect(label(Date.parse("2026-09-25T00:00:00Z"))).toBe("25 Sep");
    });

    test("within a day, midnight carries the date so the times are anchored", () => {
      const label = timeAxisFormatter(2 * DAY);

      expect(label(Date.parse("2026-11-03T00:00:00Z"))).toBe("3 Nov");
      expect(label(Date.parse("2026-11-03T06:00:00Z"))).toBe("06:00");
      expect(label(Date.parse("2026-11-03T18:00:00Z"))).toBe("18:00");
    });

    test("years for a span of years, months for a span of months", () => {
      expect(timeAxisFormatter(5 * 365 * DAY)(Date.parse("2026-09-24T00:00:00Z"))).toBe("2026");
      expect(timeAxisFormatter(200 * DAY)(Date.parse("2026-09-24T00:00:00Z"))).toBe("Sep 2026");
    });

    test("seconds only once they are what tells two points apart", () => {
      expect(timeAxisFormatter(5 * 60000)(Date.parse("2026-09-24T20:50:00Z"))).toBe("20:50");
      expect(timeAxisFormatter(60000)(Date.parse("2026-09-24T20:50:00Z"))).toBe("20:50:00");
    });
  });

  describe("the label under the pointer, and the tooltip heading", () => {
    test("a day gets its weekday and no time of day", () => {
      // Midnight on a daily bucket is not precision, it is an artefact of
      // how the day was stored -- and it was being shown as "20:00:00".
      expect(timePointerFormatter(30 * DAY)(Date.parse("2026-09-24T00:00:00Z"))).toBe("Thu 24 Sep 2026");
    });

    test("within a day it keeps the time, since that is what is being read", () => {
      expect(timePointerFormatter(2 * DAY)(Date.parse("2026-11-03T18:00:00Z"))).toBe("Tue 3 Nov, 18:00");
    });

    test("the axis and the pointer agree about which day it is", () => {
      const stamp = Date.parse("2026-09-25T00:00:00Z");

      expect(timeAxisFormatter(30 * DAY)(stamp)).toContain("25 Sep");
      expect(timePointerFormatter(30 * DAY)(stamp)).toContain("25 Sep");
    });
  });

  describe("working out the span", () => {
    test("it is the distance between the first and last point", () => {
      const span = timeSpan([
        {
          data: [
            { x: at("2026-09-01T00:00:00Z"), y: 1 },
            { x: at("2026-09-11T00:00:00Z"), y: 2 },
          ],
        },
      ]);

      expect(span).toBe(10 * DAY);
    });

    test("it spans every series, not just the first", () => {
      const span = timeSpan([
        { data: [{ x: at("2026-09-01T00:00:00Z"), y: 1 }] },
        { data: [{ x: at("2026-09-21T00:00:00Z"), y: 2 }] },
      ]);

      expect(span).toBe(20 * DAY);
    });

    test("a single point covers no time, and is not a crash", () => {
      expect(timeSpan([{ data: [{ x: at("2026-09-01T00:00:00Z"), y: 1 }] }])).toBe(0);
      expect(timeSpan([])).toBe(0);
    });
  });
});
