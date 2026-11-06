import moment from "moment";
import getOptions from "./getOptions";
import buildOption, { axisValue, bandsIn, problemWith, riverPoints } from "./buildOption";

/*
  A stacked area with no baseline.

  A stacked bar answers "how much, broken down". This answers "how is the
  mix changing", and answers it better because no band is pinned to zero --
  each is read as its own shape rather than as the gap between two moving
  lines.
*/
const columns = [{ name: "day" }, { name: "channel" }, { name: "spend" }];

function options(overrides: any = {}) {
  return getOptions({ xColumn: "day", seriesColumn: "channel", valueColumn: "spend", ...overrides }, {
    columns,
    rows: [],
  } as any);
}

describe("the streamgraph", () => {
  describe("what it refuses to draw", () => {
    test("no rows", () => {
      expect(problemWith({ rows: [] }, options())).toBeTruthy();
    });

    // Not reachable through getOptions when there are columns to fall back
    // on, which is the point: this is the state a result with one column
    // leaves it in.
    test("a column still unchosen", () => {
      const bare = { xColumn: "day", seriesColumn: "", valueColumn: "spend" } as any;

      expect(problemWith({ rows: [{}] }, bare)).toContain("Choose a column");
    });

    // Picking the same column twice draws one band, which reads as broken
    // data rather than as a chart waiting to be configured.
    test("the axis and the bands being the same column", () => {
      expect(problemWith({ rows: [{}] }, options({ seriesColumn: "day" }))).toContain("different columns");
    });

    test("and nothing wrong with a configured chart", () => {
      expect(problemWith({ rows: [{}] }, options())).toBeNull();
    });
  });

  describe("turning rows into a river", () => {
    test("one point per band per step", () => {
      const points = riverPoints(
        [
          { day: "2026-01-01", channel: "paid", spend: 10 },
          { day: "2026-01-01", channel: "organic", spend: 4 },
        ],
        options()
      );

      expect(points).toEqual([
        ["2026-01-01", 4, "organic"],
        ["2026-01-01", 10, "paid"],
      ]);
    });

    // Two rows at the same point in the same band are one thicker band.
    // Left as two, ECharts draws the second over the first and the first
    // is simply gone.
    test("two rows for the same band at the same step are added up", () => {
      const points = riverPoints(
        [
          { day: "2026-01-01", channel: "paid", spend: 10 },
          { day: "2026-01-01", channel: "paid", spend: 5 },
        ],
        options()
      );

      expect(points).toEqual([["2026-01-01", 15, "paid"]]);
    });

    test("points come out in axis order, because that is the order they are drawn in", () => {
      const points = riverPoints(
        [
          { day: "2026-01-03", channel: "paid", spend: 3 },
          { day: "2026-01-01", channel: "paid", spend: 1 },
          { day: "2026-01-02", channel: "paid", spend: 2 },
        ],
        options()
      );

      expect(points.map((p) => p[0])).toEqual(["2026-01-01", "2026-01-02", "2026-01-03"]);
    });

    test("a value that is not a number counts as nothing, not as NaN", () => {
      const points = riverPoints([{ day: "d", channel: "c", spend: "oops" }], options());

      expect(points[0][1]).toBe(0);
    });
  });

  describe("the axis value", () => {
    // Milliseconds, not a formatted string: a zone-less string means one
    // instant to ECharts under `useUTC` and another to `Date.parse`.
    test("a date becomes the instant it is", () => {
      expect(axisValue(moment.utc("2026-09-24T00:00:00Z"))).toBe(Date.parse("2026-09-24T00:00:00Z"));
    });

    test("anything else is left as the label it was", () => {
      expect(axisValue("Week 4")).toBe("Week 4");
      expect(axisValue(null)).toBe("");
    });
  });

  describe("the bands", () => {
    test("are listed in the order they first appear", () => {
      expect(
        bandsIn([
          ["a", 1, "paid"],
          ["a", 1, "organic"],
          ["b", 1, "paid"],
        ])
      ).toEqual(["paid", "organic"]);
    });
  });

  describe("the option it builds", () => {
    const data = {
      columns,
      rows: [
        { day: "2026-01-01", channel: "paid", spend: 10 },
        { day: "2026-01-02", channel: "paid", spend: 12 },
      ],
    };

    test("is a themeRiver on a single axis", () => {
      const { option } = buildOption(data, options());

      expect(option.series[0].type).toBe("themeRiver");
      expect(option.singleAxis).toBeTruthy();
    });

    test("hides the legend when asked, and leaves room for it when not", () => {
      expect(buildOption(data, options()).option.legend.show).toBe(true);
      expect(buildOption(data, options({ showLegend: false })).option.legend.show).toBe(false);
    });

    // The bands are the shape. A new set has to be rebuilt rather than
    // tweened from a set that no longer exists.
    test("changing the bands changes the signature", () => {
      const other = { ...data, rows: [{ day: "2026-01-01", channel: "email", spend: 1 }] };

      expect(buildOption(data, options()).signature).not.toBe(buildOption(other, options()).signature);
    });

    test("the same bands with new numbers can tween", () => {
      const heavier = { ...data, rows: data.rows.map((r) => ({ ...r, spend: r.spend * 2 })) };

      expect(buildOption(data, options()).signature).toBe(buildOption(heavier, options()).signature);
    });

    test("a problem means no series rather than a broken one", () => {
      const built = buildOption({ ...data, rows: [] }, options());

      expect(built.problem).toBeTruthy();
      expect(built.option.series).toEqual([]);
    });
  });
});

/*
  The time axis, which the streamgraph did not get when the chart did.

  Two faults travelled together: values parsed as UTC and drawn in the
  viewer's zone, so every daily band was a day early; and ECharts' own tick
  rhythm, which anchors one series of ticks to the data and another to each
  month and draws both -- "15, 22, 29, 5, 8, 15", weekly except where a
  month turned.
*/
describe("the streamgraph's time axis", () => {
  function overDays(days: number) {
    const start = moment.utc("2026-08-10T00:00:00Z");
    const rows: any[] = [];
    for (let d = 0; d < days; d += 1) {
      ["paid", "organic"].forEach((channel, i) => {
        rows.push({ day: start.clone().add(d, "days"), channel, revenue: 100 + d + i });
      });
    }
    return { columns, rows };
  }

  test("is drawn in the zone its values were parsed in", () => {
    expect(buildOption(overDays(30), options()).option.useUTC).toBe(true);
  });

  test("puts its ticks at even intervals, starting at the first point", () => {
    const { option } = buildOption(overDays(90), options());
    const ticks = option.singleAxis.axisLabel.customValues;

    expect(ticks[0]).toBe(Date.parse("2026-08-10T00:00:00Z"));
    const gaps = ticks.slice(1).map((at: number, i: number) => at - ticks[i]);
    expect(new Set(gaps).size).toBe(1);
  });

  test("labels them the way every other time axis is labelled", () => {
    const { option } = buildOption(overDays(90), options());

    expect(option.singleAxis.axisLabel.formatter(Date.parse("2026-09-24T00:00:00Z"))).toBe("24 Sep");
  });

  test("a chart covering no time asks for no ticks of its own", () => {
    const { option } = buildOption(overDays(1), options());

    expect(option.singleAxis.axisLabel.customValues).toBeUndefined();
  });
});
