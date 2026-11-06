import moment from "moment";
import getOptions from "./getOptions";
import buildOption, { axisLabel, candlesFrom, problemWith } from "./buildOption";

/*
  Open, close, low, high -- four numbers a line of closing prices throws
  away. A day that opened at 10, fell to 2 and recovered to 11 draws the
  same stroke as one that drifted from 10 to 11.

  The order is the thing worth pinning. Every convention in the world says
  OHLC; ECharts wants open, close, low, high. A silent transposition draws
  a plausible chart of something that never happened.
*/
const columns = [{ name: "day" }, { name: "open" }, { name: "close" }, { name: "low" }, { name: "high" }];

function options(overrides: any = {}) {
  return getOptions(
    { xColumn: "day", openColumn: "open", closeColumn: "close", lowColumn: "low", highColumn: "high", ...overrides },
    { columns, rows: [] } as any
  );
}

const day = (d: string, o: number, c: number, l: number, h: number) => ({
  day: d,
  open: o,
  close: c,
  low: l,
  high: h,
});

describe("the candlestick", () => {
  describe("what it refuses to draw", () => {
    test("no rows", () => {
      expect(problemWith({ rows: [] }, options())).toBeTruthy();
    });

    test("one of the four parts unchosen", () => {
      const bare = { xColumn: "day", openColumn: "open", closeColumn: "", lowColumn: "l", highColumn: "h" } as any;

      expect(problemWith({ rows: [{}] }, bare)).toContain("open, close, low and high");
    });

    test("and nothing wrong with a configured chart", () => {
      expect(problemWith({ rows: [{}] }, options())).toBeNull();
    });

    test("rows that have none of the four", () => {
      const built = buildOption({ columns, rows: [{ day: "a" }] }, options());

      expect(built.problem).toContain("No row has all four");
      expect(built.option.series).toEqual([]);
    });
  });

  describe("the candle", () => {
    // The whole reason this is pinned: ECharts' order is not OHLC.
    test("is [open, close, low, high], which is not the order it is named in", () => {
      const { candles } = candlesFrom([day("d", 10, 11, 2, 12)], options());

      expect(candles).toEqual([[10, 11, 2, 12]]);
    });

    test("keeps its label beside it", () => {
      const { labels } = candlesFrom([day("2026-01-01", 1, 2, 0.5, 3)], options());

      expect(labels).toEqual(["2026-01-01"]);
    });

    // A zero-filled low is a bar stretching to the axis, which reads as a
    // crash that never happened.
    test("a row missing a number is dropped rather than filled with zero", () => {
      const { candles } = candlesFrom(
        [day("a", 10, 11, 2, 12), { day: "b", open: 1, close: 2, low: null, high: 4 }],
        options()
      );

      expect(candles).toEqual([[10, 11, 2, 12]]);
    });

    test("a number arriving as text still counts", () => {
      const { candles } = candlesFrom([{ day: "a", open: "10", close: "11", low: "2", high: "12" }], options());

      expect(candles).toEqual([[10, 11, 2, 12]]);
    });
  });

  describe("the axis label", () => {
    test("a date reads as a date", () => {
      expect(axisLabel(moment.utc("2026-09-24T00:00:00Z"))).toBe("2026-09-24");
    });

    test("anything else stays the label it was", () => {
      expect(axisLabel("Week 4")).toBe("Week 4");
      expect(axisLabel(null)).toBe("");
    });
  });

  describe("the option it builds", () => {
    const data = { columns, rows: [day("a", 10, 11, 2, 12), day("b", 11, 9, 8, 13)] };

    test("is a candlestick series", () => {
      expect(buildOption(data, options()).option.series[0].type).toBe("candlestick");
    });

    // A candlestick is about the range things moved through. From zero,
    // every candle is squashed into a band at the top where none of it
    // can be read.
    test("the value axis does not start at zero", () => {
      expect(buildOption(data, options()).option.yAxis.scale).toBe(true);
    });

    test("rising and falling carry their own colours, border included", () => {
      const built = buildOption(data, options({ risingColor: "#0f0", fallingColor: "#f00" })).option.series[0];

      expect(built.itemStyle).toMatchObject({
        color: "#0f0",
        color0: "#f00",
        borderColor: "#0f0",
        borderColor0: "#f00",
      });
    });

    test("green up and red down unless somebody says otherwise", () => {
      const built = buildOption(data, options()).option.series[0];

      expect(built.itemStyle.color).toBe("#16a34a");
      expect(built.itemStyle.color0).toBe("#dc2626");
    });
  });

  describe("guessing the columns", () => {
    // Four empty selects is a worse first impression than four that need
    // correcting, and a query writes `o, c, l, h` as often as the words.
    test("the four numeric columns are taken in the order a candle is read", () => {
      const guessed = getOptions({}, {
        columns: [{ name: "day" }, { name: "o" }, { name: "c" }, { name: "l" }, { name: "h" }],
        rows: [{ day: "a", o: 1, c: 2, l: 0, h: 3 }],
      } as any);

      expect(guessed.openColumn).toBe("o");
      expect(guessed.closeColumn).toBe("c");
      expect(guessed.lowColumn).toBe("l");
      expect(guessed.highColumn).toBe("h");
    });
  });
});
