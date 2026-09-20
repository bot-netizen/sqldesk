import getOptions from "./getOptions";
import buildOption, { layout } from "./buildOption";

/*
  The day arithmetic is covered in days.test.ts. What is checked here is the
  translation into a chart: that a span crossing new year becomes two rows
  rather than one absurdly long strip, that each row is given only its own
  year's days, and that the squares are sized to the box rather than to a
  guess.
*/

const columns = [
  { name: "day", type: "date" },
  { name: "commits", type: "integer" },
];

function daysBetween(from: string, to: string, value = 1) {
  const rows = [];
  const cursor = new Date(`${from}T12:00:00`);
  const end = new Date(`${to}T12:00:00`);
  while (cursor <= end) {
    const iso = cursor.toISOString().slice(0, 10);
    rows.push({ day: iso, commits: value });
    cursor.setDate(cursor.getDate() + 1);
  }
  return rows;
}

function build(rows: any[], overrides: any = {}, size?: any) {
  const data = { columns, rows };
  return buildOption(data, getOptions({ dateColumn: "day", valueColumn: "commits", ...overrides }, data), size);
}

describe("layout", () => {
  test("squares are sized to fill the width, not squeezed by the height", () => {
    // Letting the height shrink them too left a full-width widget with a
    // small calendar in one corner and empty space beside it.
    const short = layout({ width: 1400, height: 140 }, 1, 53);
    const tall = layout({ width: 1400, height: 600 }, 1, 53);
    expect(short.cell).toBe(tall.cell);
    // And the squares really do span the width they were given.
    expect(short.cell * 53).toBeGreaterThan(1400 * 0.8);
  });

  test("a wider widget gets bigger squares", () => {
    expect(layout({ width: 1200, height: 300 }, 1, 53).cell).toBeGreaterThan(
      layout({ width: 500, height: 300 }, 1, 53).cell
    );
  });

  test("more years means a taller calendar, not smaller squares", () => {
    const one = layout({ width: 1400, height: 300 }, 1, 53);
    const three = layout({ width: 1400, height: 300 }, 3, 53);
    expect(three.cell).toBe(one.cell);
    expect(three.height).toBeGreaterThan(one.height);
  });

  test("a calendar takes the height it needs rather than being squashed", () => {
    // Three years cannot fit a short tile at a legible square size, so it asks
    // for more room and the container scrolls.
    expect(layout({ width: 1400, height: 140 }, 3, 53).height).toBeGreaterThan(140);
  });

  test("a calendar that fits fills its box rather than leaving a gap", () => {
    expect(layout({ width: 500, height: 900 }, 1, 53).height).toBe(900);
  });

  test("squares stay legible however small the box gets", () => {
    // Below this a square is a speck, and a calendar of specks says nothing.
    expect(layout({ width: 80, height: 60 }, 4, 53).cell).toBeGreaterThanOrEqual(8);
  });

  test("squares stop growing, so a tall widget is not a wall of tiles", () => {
    expect(layout({ width: 4000, height: 2000 }, 1, 12).cell).toBeLessThanOrEqual(22);
  });

  test("a year's row is seven squares tall plus its month names", () => {
    const { cell, rowHeight } = layout({ width: 800, height: 400 }, 1, 53);
    expect(rowHeight).toBeGreaterThan(cell * 7);
  });
});

describe("the calendar", () => {
  test("one square per day that has data", () => {
    const built = build(daysBetween("2024-03-01", "2024-03-10"), { range: "all" });
    expect(built.option.series[0].data).toHaveLength(10);
    expect(built.option.series[0].data[0]).toEqual(["2024-03-01", 1]);
  });

  test("a span inside one year is one calendar", () => {
    const built = build(daysBetween("2024-03-01", "2024-09-30"), { range: "all" });
    expect(built.option.calendar).toHaveLength(1);
    expect(built.option.series).toHaveLength(1);
  });

  test("a span crossing new year becomes a row per year", () => {
    // One strip of a hundred weeks is unreadable; two rows of twelve months
    // is what a reader expects.
    const built = build(daysBetween("2023-11-01", "2024-02-28"), { range: "all" });
    expect(built.option.calendar).toHaveLength(2);
    expect(built.option.calendar[0].range).toEqual(["2023-11-01", "2023-12-31"]);
    expect(built.option.calendar[1].range).toEqual(["2024-01-01", "2024-02-28"]);
  });

  test("each year's row is given only its own year's days", () => {
    // A day drawn on the wrong year's calendar is placed by ECharts anyway,
    // silently, on whatever square that date maps to in that year.
    const built = build(daysBetween("2023-12-28", "2024-01-03"), { range: "all" });
    const [first, second] = built.option.series;
    expect(first.data.every((d: any[]) => d[0].startsWith("2023"))).toBe(true);
    expect(second.data.every((d: any[]) => d[0].startsWith("2024"))).toBe(true);
    expect(first.data.length + second.data.length).toBe(7);
  });

  test("each year's series is bound to its own calendar", () => {
    const built = build(daysBetween("2023-11-01", "2024-02-28"), { range: "all" });
    expect(built.option.series.map((s: any) => s.calendarIndex)).toEqual([0, 1]);
  });

  test("years are stacked, not drawn on top of each other", () => {
    const built = build(daysBetween("2022-11-01", "2024-02-28"), { range: "all" });
    const tops = built.option.calendar.map((c: any) => c.top);
    tops.slice(1).forEach((top: number, i: number) => expect(top).toBeGreaterThan(tops[i]));
  });

  test("the colour scale runs from the quietest day to the busiest", () => {
    const rows = [
      { day: "2024-03-01", commits: 2 },
      { day: "2024-03-02", commits: 9 },
    ];
    const built = build(rows, { range: "all" });
    expect(built.option.visualMap.min).toBe(2);
    expect(built.option.visualMap.max).toBe(9);
  });

  test("a scale with no spread still has two ends", () => {
    // min equal to max makes ECharts' visualMap divide by zero and paint
    // every square the same colour as the empty ones.
    const built = build([{ day: "2024-03-01", commits: 4 }], { range: "all" });
    expect(built.option.visualMap.max).toBeGreaterThan(built.option.visualMap.min);
  });

  test("weeks can start on Monday or Sunday", () => {
    const rows = daysBetween("2024-03-01", "2024-03-10");
    expect(build(rows, { startOnMonday: true }).option.calendar[0].dayLabel.firstDay).toBe(1);
    expect(build(rows, { startOnMonday: false }).option.calendar[0].dayLabel.firstDay).toBe(0);
  });

  test("says what it could not place", () => {
    const rows = [...daysBetween("2024-03-01", "2024-03-03"), { day: null, commits: 5 }];
    expect(build(rows, { range: "all" }).note).toContain("1 row had no readable date");
  });

  describe("when there is nothing to draw", () => {
    test("no rows", () => {
      expect(build([]).problem).toBe("No rows to show.");
    });

    test("a date column that is not in the result", () => {
      expect(build(daysBetween("2024-03-01", "2024-03-02"), { dateColumn: "gone" }).problem).toBe(
        "Choose a date column in the editor."
      );
    });

    test("a column with no readable dates", () => {
      const built = build([{ day: "not a date", commits: 1 }], { range: "all" });
      expect(built.problem).toBe("No readable dates in “day”.");
    });
  });

  test("new counts for the same span can tween; a new span redraws", () => {
    const rows = daysBetween("2024-03-01", "2024-03-10");
    const same = build(rows, { range: "all" }).signature;
    const alsoSame = build(daysBetween("2024-03-01", "2024-03-10", 7), { range: "all" }).signature;
    const different = build(daysBetween("2024-03-01", "2024-04-10"), { range: "all" }).signature;
    expect(alsoSame).toBe(same);
    expect(different).not.toBe(same);
  });
});

describe("the calendar's options", () => {
  test("a new calendar finds the date column and the number beside it", () => {
    const options = getOptions({}, { columns, rows: [] });
    expect(options.dateColumn).toBe("day");
    expect(options.valueColumn).toBe("commits");
  });

  test("no value column means count the rows, and stays that way", () => {
    expect(getOptions({ valueColumn: "" }, { columns, rows: [] }).valueColumn).toBe("");
  });

  test("an unknown range falls back rather than drawing nothing", () => {
    expect(getOptions({ range: "fortnight" }, { columns, rows: [] }).range).toBe("12-months");
  });
});
