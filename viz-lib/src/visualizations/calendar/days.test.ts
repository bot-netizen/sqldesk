import buildDays, { dayOf, rangeFor, yearsIn } from "./days";

/*
  Dates are where a calendar goes wrong, and it goes wrong invisibly: a row
  landing on the day before its own because of a timezone looks like a
  perfectly ordinary calendar, just a square to the left.

  The suite runs in Africa/Khartoum (see the jest config), which is UTC+2, so
  a naive UTC reading of a date-only string would land on the day before.
*/

describe("dayOf", () => {
  test("a plain date is that day, whatever the timezone", () => {
    expect(dayOf("2024-03-05")).toBe("2024-03-05");
  });

  test("a timestamp is the day it falls on locally", () => {
    // The day the reader means is the day on their own clock.
    expect(dayOf("2024-03-05 23:30:00")).toBe("2024-03-05");
    expect(dayOf("2024-03-05T09:15:00")).toBe("2024-03-05");
  });

  test("a date object is the day it falls on", () => {
    expect(dayOf(new Date(2024, 2, 5, 12, 0, 0))).toBe("2024-03-05");
  });

  test("anything unreadable is no day at all, rather than today", () => {
    // Falling back to today would invent data on a square that has none.
    [null, undefined, "", "not a date", {}].forEach((value) => expect(dayOf(value)).toBeNull());
  });

  test("a word is refused without troubling moment about it", () => {
    // Pointing the date column at a text column is an easy mistake, and
    // moment warns once per row when asked to parse one -- hundreds of
    // deprecation warnings across a dashboard.
    const warn = jest.spyOn(console, "warn").mockImplementation(() => {});
    try {
      ["North", "not a date", "n/a"].forEach((v) => expect(dayOf(v)).toBeNull());
      expect(warn).not.toHaveBeenCalled();
    } finally {
      warn.mockRestore();
    }
  });

  test("an invalid date object is no day", () => {
    expect(dayOf(new Date("nonsense"))).toBeNull();
  });
});

describe("buildDays", () => {
  const rows = [
    { day: "2024-03-01", n: 2 },
    { day: "2024-03-01", n: 3 },
    { day: "2024-03-02", n: 5 },
  ];

  test("rows landing on the same day are added up, not replaced", () => {
    // One row per event is the ordinary case; taking the last would draw a
    // calendar of ones.
    const built = buildDays(rows, "day", "n", "all");
    expect(built.days).toEqual([
      { date: "2024-03-01", value: 5 },
      { date: "2024-03-02", value: 5 },
    ]);
  });

  test("no value column counts the rows", () => {
    const built = buildDays(rows, "day", "", "all");
    expect(built.days).toEqual([
      { date: "2024-03-01", value: 2 },
      { date: "2024-03-02", value: 1 },
    ]);
  });

  test("days come out in order, whatever order the rows arrived in", () => {
    const shuffled = [
      { day: "2024-03-09", n: 1 },
      { day: "2024-03-02", n: 1 },
      { day: "2024-03-05", n: 1 },
    ];
    expect(buildDays(shuffled, "day", "n", "all").days.map((d) => d.date)).toEqual([
      "2024-03-02",
      "2024-03-05",
      "2024-03-09",
    ]);
  });

  test("rows with no readable date are counted, not dropped silently", () => {
    const built = buildDays([...rows, { day: null, n: 9 }, { day: "gibberish", n: 9 }], "day", "n", "all");
    expect(built.undated).toBe(2);
    // And they do not contribute to any square.
    expect(built.days.reduce((sum, d) => sum + d.value, 0)).toBe(10);
  });

  test("rows with no readable value are counted too", () => {
    const built = buildDays(
      [
        { day: "2024-03-01", n: "n/a" },
        { day: "2024-03-02", n: 4 },
      ],
      "day",
      "n",
      "all"
    );
    expect(built.skipped).toBe(1);
    expect(built.days).toEqual([{ date: "2024-03-02", value: 4 }]);
  });

  test("days outside the range are left out", () => {
    const spread = [
      { day: "2023-01-15", n: 1 },
      { day: "2024-03-01", n: 1 },
      { day: "2024-03-02", n: 1 },
    ];
    const built = buildDays(spread, "day", "n", "3-months");
    expect(built.days.map((d) => d.date)).toEqual(["2024-03-01", "2024-03-02"]);
  });

  test("counts the days in range that nothing landed on", () => {
    // March has 31 days and two of them have data.
    const built = buildDays(rows, "day", "n", "all");
    expect(built.from).toBe("2024-03-01");
    expect(built.to).toBe("2024-03-02");
    expect(built.empty).toBe(0);
  });

  test("no rows is an empty calendar, not a crash", () => {
    const built = buildDays([], "day", "n", "all");
    expect(built.days).toEqual([]);
    expect(built.from <= built.to).toBe(true);
  });
});

describe("rangeFor", () => {
  const dates = ["2023-11-20", "2024-03-05", "2024-03-18"];

  test("every range ends at the newest day in the data, not at today", () => {
    // A query for last quarter should not draw empty months up to now.
    (["3-months", "12-months", "all"] as const).forEach((range) => {
      expect(rangeFor(dates, range).to).toBe("2024-03-18");
    });
  });

  test("three months covers this month and the two before it", () => {
    expect(rangeFor(dates, "3-months").from).toBe("2024-01-01");
  });

  test("twelve months covers this month and the eleven before it", () => {
    expect(rangeFor(dates, "12-months").from).toBe("2023-04-01");
  });

  test("a year is the whole calendar year the newest day sits in", () => {
    expect(rangeFor(dates, "year")).toEqual({ from: "2024-01-01", to: "2024-12-31" });
  });

  test("all is exactly what the data covers", () => {
    expect(rangeFor(dates, "all")).toEqual({ from: "2023-11-20", to: "2024-03-18" });
  });

  test("no dates still gives a range to draw", () => {
    const range = rangeFor([], "all");
    expect(range.from < range.to).toBe(true);
  });
});

describe("yearsIn", () => {
  test("one year when the span stays inside one", () => {
    expect(yearsIn("2024-03-01", "2024-09-30")).toEqual([2024]);
  });

  test("every year a span touches, so each gets its own row", () => {
    expect(yearsIn("2022-12-30", "2024-01-02")).toEqual([2022, 2023, 2024]);
  });
});
