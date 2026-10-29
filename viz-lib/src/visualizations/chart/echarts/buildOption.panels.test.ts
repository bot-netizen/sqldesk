import getOptions from "../getOptions";
import buildOption from "./buildOption";
import { MAX_PANELS, measureAxisIndex, panelCount, seriesPanel } from "../panels";

function series(name: string, type = "line") {
  return {
    name,
    type,
    data: [
      { x: "a", y: 1, $raw: { x: "a", y: 1 } },
      { x: "b", y: 2, $raw: { x: "b", y: 2 } },
    ],
  };
}

function options(overrides: any = {}) {
  return getOptions({ globalSeriesType: "line", sortX: false, ...overrides });
}

const SIZE = { width: 800, height: 600 };

/*
  Three plots down one column, sharing a clock. The picture this was asked
  for is spend over time, percent against the same bucket a week back, and a
  pair of rates -- readable only because the same x position means the same
  moment in all three.
*/
describe("Visualizations -> Chart -> ECharts -> panels", () => {
  describe("the chart that was always drawn", () => {
    test("one panel keeps the single stretching grid, not an array of one", () => {
      const built = buildOption([series("revenue")], options(), SIZE);

      expect(Array.isArray(built.option.grid)).toBe(false);
      expect(built.option.grid.top).toBe(14);
      expect(built.option.grid.bottom).toBeGreaterThan(0);
      expect(built.option.grid.height).toBeUndefined();
    });

    test("one panel has one category axis and the left/right measure pair", () => {
      const built = buildOption([series("revenue")], options(), SIZE);

      expect(Array.isArray(built.option.xAxis)).toBe(false);
      expect(built.option.yAxis).toHaveLength(2);
      expect(built.option.yAxis[1].position).toBe("right");
    });

    test("nothing links an axis pointer when there is only one plot to link", () => {
      const built = buildOption([series("revenue")], options(), SIZE);

      expect(built.option.axisPointer).toBeUndefined();
    });

    /*
      A saved chart from before this existed has no `panels` at all, and the
      editor can write a number that came back from JSON as a string.
    */
    test("a count that is missing, broken or absurd comes back as something drawable", () => {
      expect(panelCount({})).toBe(1);
      expect(panelCount({ panels: undefined })).toBe(1);
      expect(panelCount({ panels: 0 })).toBe(1);
      expect(panelCount({ panels: -3 })).toBe(1);
      expect(panelCount({ panels: "3" })).toBe(3);
      expect(panelCount({ panels: 2.7 })).toBe(2);
      expect(panelCount({ panels: 99 })).toBe(MAX_PANELS);
      expect(panelCount({ panels: NaN })).toBe(1);
    });
  });

  describe("laying the panels out", () => {
    test("three panels become three grids and three category axes", () => {
      const built = buildOption([series("revenue")], options({ panels: 3 }), SIZE);

      expect(built.option.grid).toHaveLength(3);
      expect(built.option.xAxis).toHaveLength(3);
      // Left and right for each: a series on the second axis needs one in its
      // own panel.
      expect(built.option.yAxis).toHaveLength(6);
    });

    test("they run down the page in order, without overlapping", () => {
      const built = buildOption([series("revenue")], options({ panels: 3 }), SIZE);
      const grids = built.option.grid;

      grids.forEach((grid: any, index: number) => {
        expect(grid.height).toBeGreaterThan(0);
        if (index > 0) {
          const previous = grids[index - 1];
          expect(grid.top).toBeGreaterThan(previous.top + previous.height);
        }
      });
    });

    test("the stack stays inside the chart, with the axis and legend still fitting below", () => {
      const built = buildOption([series("revenue")], options({ panels: 3 }), SIZE);
      const last = built.option.grid[2];

      expect(built.option.grid[0].top).toBeGreaterThanOrEqual(0);
      expect(last.top + last.height).toBeLessThan(SIZE.height);
    });

    test("equal panels get equal heights", () => {
      const built = buildOption([series("revenue")], options({ panels: 3 }), SIZE);
      const heights = built.option.grid.map((g: any) => Math.round(g.height));

      expect(new Set(heights).size).toBe(1);
    });

    /*
      The container is measured a frame after the first render. Until then
      there is no height to divide, and a panel must still be given one.
    */
    test("an unmeasured chart still lays its panels out", () => {
      const built = buildOption([series("revenue")], options({ panels: 3 }), undefined);

      expect(built.option.grid).toHaveLength(3);
      built.option.grid.forEach((grid: any) => expect(grid.height).toBeGreaterThan(0));
    });

    test("a chart too short to divide still draws every panel it was told to", () => {
      const built = buildOption([series("revenue")], options({ panels: 4 }), { width: 400, height: 120 });

      // Not collapsed to one: a chart that quietly ignored the setting gives
      // no hint that a taller widget is the fix.
      expect(built.option.grid).toHaveLength(4);
      built.option.grid.forEach((grid: any) => expect(grid.height).toBeGreaterThan(0));
    });
  });

  describe("putting a series in a panel", () => {
    test("a series draws in the panel it was given, on that panel's axis", () => {
      const built = buildOption(
        [series("spend"), series("change"), series("ecpm")],
        options({
          panels: 3,
          seriesOptions: {
            spend: { type: "line", panel: 0 },
            change: { type: "line", panel: 1 },
            ecpm: { type: "line", panel: 2 },
          },
        }),
        SIZE
      );

      expect(built.option.series.map((s: any) => s.xAxisIndex)).toEqual([0, 1, 2]);
      expect(built.option.series.map((s: any) => s.yAxisIndex)).toEqual([0, 2, 4]);
    });

    test("the right-hand axis of a panel is that panel's, not the chart's second", () => {
      const built = buildOption(
        [series("deal"), series("open")],
        options({
          panels: 2,
          seriesOptions: {
            deal: { type: "line", panel: 1, yAxis: 0 },
            open: { type: "line", panel: 1, yAxis: 1 },
          },
        }),
        SIZE
      );

      expect(built.option.series[0].yAxisIndex).toBe(measureAxisIndex(1, 0));
      expect(built.option.series[1].yAxisIndex).toBe(measureAxisIndex(1, 1));
      expect(built.option.yAxis[measureAxisIndex(1, 1)].position).toBe("right");
      expect(built.option.yAxis[measureAxisIndex(1, 1)].gridIndex).toBe(1);
    });

    test("every panel's axes point at that panel's grid", () => {
      const built = buildOption([series("revenue")], options({ panels: 3 }), SIZE);

      expect(built.option.xAxis.map((a: any) => a.gridIndex)).toEqual([0, 1, 2]);
      expect(built.option.yAxis.map((a: any) => a.gridIndex)).toEqual([0, 0, 1, 1, 2, 2]);
    });

    /*
      Turning the count down from three to two leaves a series pointing at a
      panel that no longer exists. It has to be drawn somewhere, and the top
      panel is where it can be seen and moved.
    */
    test("a series whose panel was deleted comes back to the first one", () => {
      const built = buildOption(
        [series("stranded")],
        options({ panels: 2, seriesOptions: { stranded: { type: "line", panel: 5 } } }),
        SIZE
      );

      expect(built.option.series[0].xAxisIndex).toBe(0);
      expect(built.option.series[0].yAxisIndex).toBe(0);
    });

    test("a panel that is missing, negative or not a number reads as the first", () => {
      const opts = options({ panels: 3, seriesOptions: { a: {}, b: { panel: -1 }, c: { panel: "x" } } });

      expect(seriesPanel("a", opts, 3)).toBe(0);
      expect(seriesPanel("b", opts, 3)).toBe(0);
      expect(seriesPanel("c", opts, 3)).toBe(0);
    });

    test("a panel choice is ignored entirely when the chart draws one panel", () => {
      const opts = options({ seriesOptions: { a: { panel: 2 } } });

      expect(seriesPanel("a", opts, 1)).toBe(0);
    });
  });

  describe("what the panels share", () => {
    test("one cursor spans the stack", () => {
      const built = buildOption([series("revenue")], options({ panels: 3 }), SIZE);

      expect(built.option.axisPointer).toEqual({ link: [{ xAxisIndex: "all" }] });
    });

    test("the x labels and title are on the bottom panel only", () => {
      const built = buildOption(
        [series("revenue")],
        options({ panels: 3, xAxis: { type: "category", title: { text: "Hour" }, labels: { enabled: true } } }),
        SIZE
      );

      expect(built.option.xAxis[0].axisLabel.show).toBe(false);
      expect(built.option.xAxis[1].axisLabel.show).toBe(false);
      expect(built.option.xAxis[2].axisLabel.show).toBe(true);
      expect(built.option.xAxis[0].name).toBeUndefined();
      expect(built.option.xAxis[2].name).toBe("Hour");
    });

    test("turning x labels off leaves them off on the bottom panel too", () => {
      const built = buildOption(
        [series("revenue")],
        options({ panels: 2, xAxis: { type: "category", labels: { enabled: false } } }),
        SIZE
      );

      expect(built.option.xAxis[1].axisLabel.show).toBe(false);
    });

    test("zooming moves every panel, because they are one axis", () => {
      const built = buildOption([series("revenue")], options({ panels: 3, zoom: "both" }), SIZE);

      expect(built.option.dataZoom.length).toBeGreaterThan(0);
      built.option.dataZoom.forEach((z: any) => expect(z.xAxisIndex).toEqual([0, 1, 2]));
    });

    test("one panel zooms the way it always did", () => {
      const built = buildOption([series("revenue")], options({ zoom: "slider" }), SIZE);

      expect(built.option.dataZoom[0].xAxisIndex).toBe(0);
    });
  });

  describe("how short a panel is", () => {
    /*
      Label thinning is driven by the plot's height, and a panel is a fraction
      of the chart. Without this a three-way split carried a full chart's worth
      of labels in a third of the room.
    */
    test("a short panel carries fewer value labels than the whole chart would", () => {
      const tall = buildOption([series("revenue")], options(), SIZE);
      const split = buildOption([series("revenue")], options({ panels: 4 }), SIZE);

      expect(split.option.yAxis[0].splitNumber).toBeLessThan(tall.option.yAxis[0].splitNumber);
      expect(split.option.yAxis[0].splitNumber).toBeGreaterThanOrEqual(2);
    });

    test("an unmeasured chart thins nothing, panels or not", () => {
      const built = buildOption([series("revenue")], options({ panels: 3 }), undefined);

      built.option.yAxis.forEach((axis: any) => expect(axis.splitNumber).toBeUndefined());
    });

    /*
      Each panel measures a different thing, so one title repeated down the
      stack would label two of them wrongly. Per-panel titles were built and
      cut; the chart-wide title stays on the first panel.
    */
    test("the chart-wide y title stays on the first panel", () => {
      const built = buildOption(
        [series("revenue")],
        options({ panels: 3, yAxis: [{ type: "linear", title: { text: "Dollars" } }, { type: "linear" }] }),
        SIZE
      );

      expect(built.option.yAxis[measureAxisIndex(0, 0)].name).toBe("Dollars");
      expect(built.option.yAxis[measureAxisIndex(1, 0)].name).toBeUndefined();
      expect(built.option.yAxis[measureAxisIndex(2, 0)].name).toBeUndefined();
    });
  });

  describe("the charts panels do not apply to", () => {
    test("a pie has no grid to divide", () => {
      const built = buildOption([series("revenue", "pie")], options({ globalSeriesType: "pie", panels: 3 }), SIZE);

      expect(built.option.grid).toBeUndefined();
      expect(built.option.axisPointer).toBeUndefined();
    });

    test("a sideways bar chart runs its categories down the axis panels would cut", () => {
      const built = buildOption(
        [series("revenue", "column")],
        options({ globalSeriesType: "column", swappedAxes: true, panels: 3 }),
        SIZE
      );

      expect(Array.isArray(built.option.grid)).toBe(false);
      expect(built.option.axisPointer).toBeUndefined();
      expect(built.option.yAxis).toHaveLength(1);
    });

    test("a box plot is a distribution per category, not a series over time", () => {
      const built = buildOption([series("revenue", "box")], options({ globalSeriesType: "box", panels: 3 }), SIZE);

      expect(Array.isArray(built.option.grid)).toBe(false);
    });

    test("a heatmap keeps the grid it builds for its colour scale", () => {
      const built = buildOption(
        [series("revenue", "heatmap")],
        options({ globalSeriesType: "heatmap", panels: 3 }),
        SIZE
      );

      expect(Array.isArray(built.option.grid)).toBe(false);
      expect(built.option.grid.bottom).toBe(60);
    });
  });

  describe("redrawing rather than animating", () => {
    test("moving a series to another panel changes the shape, so the chart is rebuilt", () => {
      const before = buildOption(
        [series("revenue")],
        options({ panels: 2, seriesOptions: { revenue: { type: "line", panel: 0 } } }),
        SIZE
      );
      const after = buildOption(
        [series("revenue")],
        options({ panels: 2, seriesOptions: { revenue: { type: "line", panel: 1 } } }),
        SIZE
      );

      expect(before.signature).not.toEqual(after.signature);
    });

    test("changing the panel count changes the shape", () => {
      const one = buildOption([series("revenue")], options(), SIZE);
      const three = buildOption([series("revenue")], options({ panels: 3 }), SIZE);

      expect(one.signature).not.toEqual(three.signature);
    });

    test("a one-panel chart's shape is unchanged by this existing at all", () => {
      const built = buildOption([series("revenue")], options(), SIZE);

      expect(JSON.parse(built.signature).panels).toBe(1);
    });
  });
});
