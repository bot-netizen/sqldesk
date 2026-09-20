import buildSpans, { timeOf, MIN_SPAN_MS } from "./spans";

/*
  Time is where a timeline goes wrong. A span with its ends the wrong way
  round draws as nothing at all; a run that has not finished has no end to
  read, and dropping it would make a live incident vanish from the very chart
  meant to show it.
*/

const NOW = Date.parse("2024-03-05T12:00:00Z");

const base = {
  laneColumn: "service",
  startColumn: "started",
  endColumn: "ended",
  durationColumn: "",
  stateColumn: "status",
  now: NOW,
};

function spans(rows: any[], overrides: any = {}) {
  return buildSpans({ rows, ...base, ...overrides });
}

describe("timeOf", () => {
  test("reads a timestamp", () => {
    expect(timeOf("2024-03-05T12:00:00Z")).toBe(NOW);
  });

  test("reads a date object", () => {
    expect(timeOf(new Date(NOW))).toBe(NOW);
  });

  test("anything unreadable is no time, rather than now", () => {
    // Falling back to now would put every unreadable row at the right-hand
    // edge, which reads as real data.
    [null, undefined, "", "not a time", {}, []].forEach((value) => expect(timeOf(value)).toBeNull());
  });
});

describe("buildSpans", () => {
  const rows = [
    { service: "api", started: "2024-03-05T10:00:00Z", ended: "2024-03-05T10:30:00Z", status: "ok" },
    { service: "api", started: "2024-03-05T11:00:00Z", ended: "2024-03-05T11:15:00Z", status: "down" },
    { service: "db", started: "2024-03-05T10:15:00Z", ended: "2024-03-05T11:45:00Z", status: "ok" },
  ];

  test("one bar per row, on the lane its label names", () => {
    const built = spans(rows);
    expect(built.spans).toHaveLength(3);
    expect(built.lanes).toEqual(["api", "db"]);
  });

  test("lanes keep the order they first appear in", () => {
    // Sorting them would shuffle a timeline someone ordered deliberately in
    // their query.
    expect(spans([...rows].reverse()).lanes).toEqual(["db", "api"]);
  });

  test("a bar runs from its start to its end", () => {
    const [first] = spans(rows).spans;
    expect(first.from).toBe(Date.parse("2024-03-05T10:00:00Z"));
    expect(first.to).toBe(Date.parse("2024-03-05T10:30:00Z"));
    expect(first.open).toBe(false);
  });

  test("a run with no end is still running, and is drawn up to now", () => {
    const built = spans([{ service: "api", started: "2024-03-05T11:50:00Z", ended: null, status: "down" }]);
    expect(built.spans[0].to).toBe(NOW);
    expect(built.spans[0].open).toBe(true);
  });

  test("ends the wrong way round are put right rather than drawing nothing", () => {
    const built = spans([{ service: "api", started: "2024-03-05T11:00:00Z", ended: "2024-03-05T10:00:00Z" }]);
    expect(built.spans[0].from).toBe(Date.parse("2024-03-05T10:00:00Z"));
    expect(built.spans[0].to).toBe(Date.parse("2024-03-05T11:00:00Z"));
  });

  test("an instant is still wide enough to see", () => {
    const at = "2024-03-05T10:00:00Z";
    const built = spans([{ service: "api", started: at, ended: at }]);
    expect(built.spans[0].to - built.spans[0].from).toBe(MIN_SPAN_MS);
  });

  test("a duration column stands in for an end", () => {
    const built = spans([{ service: "api", started: "2024-03-05T10:00:00Z", secs: 90 }], {
      endColumn: "",
      durationColumn: "secs",
    });
    expect(built.spans[0].to - built.spans[0].from).toBe(90 * 1000);
    expect(built.spans[0].open).toBe(false);
  });

  test("an unreadable duration means still running, not zero length", () => {
    const built = spans([{ service: "api", started: "2024-03-05T11:50:00Z", secs: "n/a" }], {
      endColumn: "",
      durationColumn: "secs",
    });
    expect(built.spans[0].open).toBe(true);
    expect(built.spans[0].to).toBe(NOW);
  });

  test("rows with no readable start are counted, not placed", () => {
    const built = spans([...rows, { service: "api", started: null }]);
    expect(built.undated).toBe(1);
    expect(built.spans).toHaveLength(3);
  });

  test("the span covers everything drawn", () => {
    const built = spans(rows);
    expect(built.from).toBe(Date.parse("2024-03-05T10:00:00Z"));
    expect(built.to).toBe(Date.parse("2024-03-05T11:45:00Z"));
  });

  test("no lane column puts everything on one track", () => {
    expect(spans(rows, { laneColumn: "" }).lanes).toEqual([""]);
  });

  test("no rows is an empty timeline, not a crash", () => {
    const built = spans([]);
    expect(built.spans).toEqual([]);
    expect(built.lanes).toEqual([]);
    expect(built.from).toBe(NOW);
  });
});
