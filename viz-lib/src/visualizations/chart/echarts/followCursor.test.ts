import { nearestSeries, pointAt, FOLLOW_RADIUS, followCursor } from "./followCursor";

/*
  On a chart with a dozen lines, the axis tooltip lists all twelve in the
  same weight and leaves you matching a colour swatch against a line. These
  pin the part that decides which one you meant.
*/
describe("the line the cursor is reading", () => {
  describe("picking it", () => {
    test("the nearest one", () => {
      const at = [
        { seriesIndex: 0, y: 100 },
        { seriesIndex: 1, y: 160 },
        { seriesIndex: 2, y: 300 },
      ];

      expect(nearestSeries(at, 150, FOLLOW_RADIUS)).toBe(1);
      expect(nearestSeries(at, 105, FOLLOW_RADIUS)).toBe(0);
    });

    // Otherwise running the cursor along the empty top of a plot picks out
    // whichever series happens to be highest, and the chart spends its time
    // pointing at something nobody asked about.
    test("nothing at all when the cursor is near no line", () => {
      const at = [{ seriesIndex: 0, y: 100 }];

      expect(nearestSeries(at, 100 + FOLLOW_RADIUS + 1, FOLLOW_RADIUS)).toBeNull();
      expect(nearestSeries(at, 100 + FOLLOW_RADIUS, FOLLOW_RADIUS)).toBe(0);
    });

    test("a series with no point here is skipped, not treated as zero", () => {
      const at = [
        { seriesIndex: 0, y: null },
        { seriesIndex: 1, y: 120 },
      ];

      expect(nearestSeries(at, 118, FOLLOW_RADIUS)).toBe(1);
    });

    test("nothing to pick from is not a crash", () => {
      expect(nearestSeries([], 100, FOLLOW_RADIUS)).toBeNull();
      expect(nearestSeries([{ seriesIndex: 0, y: null }], 100, FOLLOW_RADIUS)).toBeNull();
    });

    // Two lines crossing share a pixel. Whichever is picked, it has to be
    // the same one on the next mouse move, or the highlight strobes.
    test("ties go to the earlier series, so an overlap does not flicker", () => {
      const at = [
        { seriesIndex: 0, y: 200 },
        { seriesIndex: 1, y: 200 },
      ];

      expect(nearestSeries(at, 200, FOLLOW_RADIUS)).toBe(0);
    });
  });

  describe("finding a series' value under the pointer", () => {
    test("a category axis reports an index, and the data is bare numbers", () => {
      expect(pointAt({ data: [5, 9, 2] }, { dataIndex: 1 })).toEqual([1, 9]);
    });

    test("a time axis reports a value, and the data is pairs", () => {
      const series = {
        data: [
          [1000, 5],
          [2000, 9],
        ],
      };

      expect(pointAt(series, { value: 2000 })).toEqual([2000, 9]);
    });

    test("a gap in a series is no point rather than a point at zero", () => {
      expect(pointAt({ data: [5, null, 2] }, { dataIndex: 1 })).toBeNull();
      expect(pointAt({ data: [[1000, 5]] }, { value: 9999 })).toBeNull();
    });

    test("an empty series has nothing under the pointer", () => {
      expect(pointAt({ data: [] }, { dataIndex: 0 })).toBeNull();
      expect(pointAt({}, { dataIndex: 0 })).toBeNull();
    });
  });

  describe("wiring it to a chart", () => {
    function fakeChart(series: any[]) {
      const zr: any = {
        handlers: {},
        on(n: string, f: any) {
          this.handlers[n] = f;
        },
        off(n: string) {
          delete this.handlers[n];
        },
      };
      const chart: any = {
        handlers: {} as any,
        actions: [] as any[],
        getZr: () => zr,
        getOption: () => ({ series }),
        convertToPixel: (_: any, point: any) => [0, point[1]],
        dispatchAction: (a: any) => chart.actions.push(a),
        on(n: string, f: any) {
          chart.handlers[n] = f;
        },
        off(n: string) {
          delete chart.handlers[n];
        },
      };
      return { chart, zr };
    }

    test("highlights the nearest line as the pointer moves", () => {
      const { chart, zr } = fakeChart([{ data: [[1000, 100]] }, { data: [[1000, 300]] }]);
      followCursor(chart);

      zr.handlers.mousemove({ offsetY: 95 });
      chart.handlers.updateAxisPointer({ axesInfo: [{ value: 1000 }] });

      expect(chart.actions).toEqual([{ type: "highlight", seriesIndex: 0 }]);
    });

    test("moves the highlight rather than lighting up two at once", () => {
      const { chart, zr } = fakeChart([{ data: [[1000, 100]] }, { data: [[1000, 300]] }]);
      followCursor(chart);

      zr.handlers.mousemove({ offsetY: 95 });
      chart.handlers.updateAxisPointer({ axesInfo: [{ value: 1000 }] });
      zr.handlers.mousemove({ offsetY: 305 });
      chart.handlers.updateAxisPointer({ axesInfo: [{ value: 1000 }] });

      expect(chart.actions).toEqual([
        { type: "highlight", seriesIndex: 0 },
        { type: "downplay", seriesIndex: 0 },
        { type: "highlight", seriesIndex: 1 },
      ]);
    });

    test("a single series has nothing to pick between, so it is left alone", () => {
      const { chart, zr } = fakeChart([{ data: [[1000, 100]] }]);
      followCursor(chart);

      zr.handlers.mousemove({ offsetY: 100 });
      chart.handlers.updateAxisPointer({ axesInfo: [{ value: 1000 }] });

      expect(chart.actions).toEqual([]);
    });

    test("leaving the chart puts it back", () => {
      const { chart, zr } = fakeChart([{ data: [[1000, 100]] }, { data: [[1000, 300]] }]);
      followCursor(chart);

      zr.handlers.mousemove({ offsetY: 95 });
      chart.handlers.updateAxisPointer({ axesInfo: [{ value: 1000 }] });
      zr.handlers.globalout();

      expect(chart.actions[chart.actions.length - 1]).toEqual({ type: "downplay", seriesIndex: 0 });
    });

    test("disposing unhooks everything and leaves nothing lit", () => {
      const { chart, zr } = fakeChart([{ data: [[1000, 100]] }, { data: [[1000, 300]] }]);
      const stop = followCursor(chart);

      zr.handlers.mousemove({ offsetY: 95 });
      chart.handlers.updateAxisPointer({ axesInfo: [{ value: 1000 }] });
      stop();

      expect(chart.actions[chart.actions.length - 1]).toEqual({ type: "downplay", seriesIndex: 0 });
      expect(Object.keys(zr.handlers)).toEqual([]);
      expect(Object.keys(chart.handlers)).toEqual([]);
    });
  });
});
