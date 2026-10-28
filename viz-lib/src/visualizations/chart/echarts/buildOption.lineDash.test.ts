import getOptions from "../getOptions";
import buildOption from "./buildOption";
import { LINE_DASHES, dashPattern, hasLineDash } from "../lineDash";

function series(name: string, points: [any, any][]) {
  return {
    name,
    type: "line",
    data: points.map(([x, y]) => ({ x, y, $raw: { x, y } })),
  };
}

function options(overrides: any = {}) {
  return getOptions({ globalSeriesType: "line", sortX: false, ...overrides });
}

const POINTS: [any, any][] = [
  ["a", 2],
  ["b", 3],
];

/*
  Two series of the same measure -- this week and last -- are told apart by
  pattern rather than by colour, because a second colour says "a different
  thing" when the truth is "the same thing, earlier".
*/
describe("Visualizations -> Chart -> ECharts -> line dash", () => {
  test("a series with no choice is solid", () => {
    const built = buildOption([series("revenue", POINTS)], options());

    expect(built.option.series[0].lineStyle).toEqual({ type: "solid" });
  });

  test("a series takes the pattern it was given", () => {
    const built = buildOption(
      [series("revenue", POINTS)],
      options({ seriesOptions: { revenue: { type: "line", dash: "dashed" } } })
    );

    expect(built.option.series[0].lineStyle.type).toEqual([8, 5]);
  });

  test("each series keeps its own, so one colour can carry two lines", () => {
    const built = buildOption(
      [series("this week", POINTS), series("last week", POINTS)],
      options({
        seriesOptions: {
          "this week": { type: "line", dash: "solid" },
          "last week": { type: "line", dash: "dotted" },
        },
      })
    );

    expect(built.option.series[0].lineStyle.type).toBe("solid");
    expect(built.option.series[1].lineStyle.type).toEqual([2, 4]);
  });

  test("an area's border dashes too, which is half of why it was asked for", () => {
    const built = buildOption(
      [series("revenue", POINTS)],
      options({ globalSeriesType: "area", seriesOptions: { revenue: { type: "area", dash: "long" } } })
    );

    expect(built.option.series[0].areaStyle).toBeDefined();
    expect(built.option.series[0].lineStyle.type).toEqual([18, 7]);
  });

  /*
    Options go into a live chart with notMerge: false, so a property the new
    option leaves out keeps whatever the last one set. Going back to Solid
    has to say so, or the line stays dashed -- the same trap `step` and
    `smooth` are commented for.
  */
  test("choosing solid again states it, rather than leaving the dash in place", () => {
    const dashed = buildOption(
      [series("revenue", POINTS)],
      options({ seriesOptions: { revenue: { type: "line", dash: "dash-dot" } } })
    );
    const back = buildOption([series("revenue", POINTS)], options({ seriesOptions: { revenue: { type: "line" } } }));

    expect(dashed.option.series[0].lineStyle.type).toEqual([12, 5, 2, 5]);
    expect(back.option.series[0].lineStyle).toEqual({ type: "solid" });
  });

  test("a bar has no line to dash and is not given one", () => {
    const built = buildOption(
      [series("revenue", POINTS)],
      options({ globalSeriesType: "column", seriesOptions: { revenue: { type: "column", dash: "dotted" } } })
    );

    expect(built.option.series[0].lineStyle).toBeUndefined();
  });

  describe("the patterns themselves", () => {
    test("a saved chart from before this existed draws solid, not dots", () => {
      expect(dashPattern(undefined)).toBe("solid");
      expect(dashPattern("")).toBe("solid");
      expect(dashPattern("squiggle")).toBe("solid");
    });

    test("every offered pattern resolves to something ECharts understands", () => {
      LINE_DASHES.forEach(({ value, pattern }) => {
        expect(dashPattern(value)).toEqual(pattern);
      });
    });

    test("no two patterns are the same, or the picker is lying", () => {
      const drawn = LINE_DASHES.map(({ pattern }) => JSON.stringify(pattern));

      expect(new Set(drawn).size).toBe(LINE_DASHES.length);
    });

    /*
      A pattern whose gaps close up at the width a chart draws at reads as a
      solid line with a texture, which is the failure this feature exists to
      avoid. Four pixels is the gap that still shows against a 2px stroke.
    */
    test("every gap stays open at the width a chart line is drawn at", () => {
      LINE_DASHES.filter(({ pattern }) => Array.isArray(pattern)).forEach(({ value, pattern }) => {
        const gaps = (pattern as number[]).filter((unused, i) => i % 2 === 1);

        expect([value, Math.min(...gaps)]).toEqual([value, expect.any(Number)]);
        expect(Math.min(...gaps)).toBeGreaterThanOrEqual(4);
      });
    });

    test("a dot is shorter than the gap after it, or it is just a short dash", () => {
      const dots = LINE_DASHES.filter(({ value }) => value === "dotted" || value === "fine");

      expect(dots).toHaveLength(2);
      dots.forEach(({ value, pattern }) => {
        const [mark, gap] = pattern as number[];

        expect([value, mark < gap]).toEqual([value, true]);
      });
    });

    test("only a line and an area have a line to dash", () => {
      expect(hasLineDash("line")).toBe(true);
      expect(hasLineDash("area")).toBe(true);
      expect(hasLineDash("column")).toBe(false);
      expect(hasLineDash("scatter")).toBe(false);
      expect(hasLineDash(undefined)).toBe(false);
    });
  });
});
