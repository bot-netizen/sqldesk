import getOptions from "../getOptions";
import buildOption, { MAX_LABELLED_CATEGORIES, categoryLabelRotation } from "./buildOption";

function options(overrides: any = {}) {
  return getOptions({ sortX: false, globalSeriesType: "column", ...overrides });
}

function bars(labels: any[]) {
  return [
    {
      name: "revenue",
      type: "column",
      data: labels.map((x, i) => ({ x, y: (i + 1) * 100, $raw: { x } })),
    },
  ];
}

const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"];

describe("Visualizations -> Chart -> ECharts -> a label for every bar", () => {
  test("every category is labelled, not just the ones that happen to fit", () => {
    // ECharts' default drops whichever labels would collide, which on a bar
    // chart leaves bars with nothing under them.
    const built = buildOption(bars(months), options());

    expect(built.option.xAxis.axisLabel.interval).toBe(0);
    expect(built.option.xAxis.axisLabel.hideOverlap).toBe(false);
  });

  test("numeric x values become categories, so each bar gets its own label", () => {
    // This is the case from the report: a numeric axis put its ticks at round
    // numbers, which do not line up with the bars.
    const built = buildOption(bars([1, 2, 3, 4, 5, 6, 7, 8]), options({ xAxis: { type: "linear" } }));

    expect(built.option.xAxis.type).toBe("category");
    expect(built.option.xAxis.data).toEqual(["1", "2", "3", "4", "5", "6", "7", "8"]);
    expect(built.option.xAxis.axisLabel.interval).toBe(0);
  });

  test("a line is left alone: it is a position on a continuum, not a bar", () => {
    const built = buildOption(bars([1, 2, 3]), options({ globalSeriesType: "line", xAxis: { type: "linear" } }));

    expect(built.option.xAxis.type).toBe("value");
    expect(built.option.xAxis.axisLabel.interval).toBeUndefined();
  });

  test("a date axis keeps its gaps, which evenly spaced categories would hide", () => {
    // Two readings a month apart are not two adjacent bars.
    const built = buildOption(bars(["2026-01-01", "2026-02-01"]), options({ xAxis: { type: "datetime" } }));

    expect(built.option.xAxis.type).toBe("time");
  });

  describe("tipping the labels so they all fit", () => {
    test("a handful of short labels stay upright", () => {
      expect(categoryLabelRotation(months)).toBe(0);
      expect(buildOption(bars(months), options()).option.xAxis.axisLabel.rotate).toBe(0);
    });

    test("many labels tip rather than overlap", () => {
      const many = Array.from({ length: 20 }, (_, i) => `Category ${i}`);

      expect(categoryLabelRotation(many)).toBeGreaterThan(0);
    });

    test("45 degrees and no steeper", () => {
      // Checked against the real renderer: upright labels collide well before
      // this, and at 90 they read bottom-to-top, which is worse than tilted.
      const crowded = Array.from({ length: 60 }, (_, i) => `Region ${i}`);

      expect(categoryLabelRotation(crowded)).toBe(45);
    });

    test("rotation only grows with crowding", () => {
      const label = (i: number) => `Category ${i}`;
      const sizes = [4, 10, 20, 40, 80];
      const rotations = sizes.map((n) => categoryLabelRotation(Array.from({ length: n }, (_, i) => label(i))));

      rotations.forEach((r, i) => {
        if (i > 0) {
          expect(r).toBeGreaterThanOrEqual(rotations[i - 1]);
        }
      });
    });

    test("past a point a label each is illegible at any angle, so ECharts picks again", () => {
      const tooMany = Array.from({ length: MAX_LABELLED_CATEGORIES + 1 }, (_, i) => `Region ${i}`);
      const built = buildOption(bars(tooMany), options());

      expect(built.option.xAxis.axisLabel.interval).toBeUndefined();
      expect(built.option.xAxis.axisLabel.hideOverlap).toBe(true);
    });

    test("right up to that point, every bar still gets one", () => {
      const many = Array.from({ length: MAX_LABELLED_CATEGORIES }, (_, i) => `Region ${i}`);
      const built = buildOption(bars(many), options());

      expect(built.option.xAxis.axisLabel.interval).toBe(0);
    });

    test("on its side the labels stack down the axis, so they never need tipping", () => {
      const many = Array.from({ length: 30 }, (_, i) => `Category ${i}`);
      const built = buildOption(bars(many), options({ swappedAxes: true }));

      expect(built.option.yAxis[0].axisLabel.rotate).toBe(0);
      expect(built.option.yAxis[0].axisLabel.interval).toBe(0);
    });
  });
});
