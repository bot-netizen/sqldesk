import moment from "moment";
import getOptions from "../getOptions";
import { echartsAxisType } from "./utils";
import buildOption, { valueAxisSplitNumber } from "./buildOption";

function series(name: string, points: [any, any][]) {
  return {
    name,
    type: "column",
    data: points.map(([x, y]) => ({ x, y, $raw: { x, y } })),
  };
}

// sortX is on by default and would reorder categories alphabetically, which
// makes the expectations below harder to read than the behaviour warrants.
function options(overrides: any = {}) {
  return getOptions({ globalSeriesType: "column", sortX: false, ...overrides });
}

describe("Visualizations -> Chart -> ECharts -> buildOption", () => {
  describe("identity", () => {
    test("every series gets an id that survives a data change", () => {
      const before = buildOption([series("revenue", [["a", 2]])], options());
      const after = buildOption([series("revenue", [["a", 4]])], options());

      expect(before.option.series[0].id).toBe("series:revenue");
      expect(after.option.series[0].id).toBe(before.option.series[0].id);
    });

    test("a value change keeps the signature, so the update is merged and animates", () => {
      const before = buildOption(
        [
          series("revenue", [
            ["a", 2],
            ["b", 3],
          ]),
        ],
        options()
      );
      const after = buildOption(
        [
          series("revenue", [
            ["a", 4],
            ["b", 3],
          ]),
        ],
        options()
      );

      expect(after.signature).toBe(before.signature);
      expect(after.option.series[0].data).toEqual([4, 3]);
    });

    test("a new category changes the signature, so the chart is replaced instead", () => {
      // Merging here would tween between values that are not the same thing.
      const before = buildOption([series("revenue", [["a", 2]])], options());
      const after = buildOption(
        [
          series("revenue", [
            ["a", 2],
            ["b", 5],
          ]),
        ],
        options()
      );

      expect(after.signature).not.toBe(before.signature);
    });

    test("a renamed series changes the signature", () => {
      const before = buildOption([series("revenue", [["a", 2]])], options());
      const after = buildOption([series("profit", [["a", 2]])], options());

      expect(after.signature).not.toBe(before.signature);
    });
  });

  describe("data shaping", () => {
    test("series are aligned to the shared category list, with gaps left empty", () => {
      const built = buildOption(
        [
          series("revenue", [
            ["a", 1],
            ["b", 2],
          ]),
          series("profit", [
            ["b", 3],
            ["c", 4],
          ]),
        ],
        options()
      );

      expect(built.option.xAxis.data).toEqual(["a", "b", "c"]);
      expect(built.option.series[0].data).toEqual([1, 2, null]);
      expect(built.option.series[1].data).toEqual([null, 3, 4]);
    });

    test("repeated x values are summed", () => {
      const built = buildOption(
        [
          series("revenue", [
            ["a", 1],
            ["a", 2],
            ["b", 5],
          ]),
        ],
        options()
      );

      expect(built.option.xAxis.data).toEqual(["a", "b"]);
      expect(built.option.series[0].data).toEqual([3, 5]);
    });

    test("missing values become zero only when the option says so", () => {
      const zeroed = buildOption([series("revenue", [["a", null]])], options({ missingValuesAsZero: true }));
      const left = buildOption([series("revenue", [["a", null]])], options({ missingValuesAsZero: false }));

      expect(zeroed.option.series[0].data).toEqual([0]);
      expect(left.option.series[0].data).toEqual([null]);
    });

    test("percent stacking normalises each category to 100", () => {
      const built = buildOption(
        [series("a", [["x", 1]]), series("b", [["x", 3]])],
        options({ series: { percentValues: true } })
      );

      expect(built.option.series[0].data).toEqual([25]);
      expect(built.option.series[1].data).toEqual([75]);
    });

    test("numeric x values get a value axis and x/y pairs", () => {
      // A line is a position on a continuum, so its axis stays numeric.
      const built = buildOption(
        [
          series("revenue", [
            [1, 10],
            [2, 20],
          ]),
        ],
        options({ globalSeriesType: "line", xAxis: { type: "-" } })
      );

      expect(built.option.xAxis.type).toBe("value");
      expect(built.option.series[0].data).toEqual([
        [1, 10],
        [2, 20],
      ]);
    });

    test("a bar chart turns those numbers into categories, so every bar is labelled", () => {
      const built = buildOption(
        [
          series("revenue", [
            [1, 10],
            [2, 20],
          ]),
        ],
        options({ xAxis: { type: "-" } })
      );

      expect(built.option.xAxis.type).toBe("category");
      expect(built.option.xAxis.data).toEqual(["1", "2"]);
      expect(built.option.series[0].data).toEqual([10, 20]);
    });
  });

  describe("options that authors set", () => {
    test("per-series overrides win over the global settings", () => {
      const built = buildOption(
        [series("revenue", [["a", 1]])],
        options({ seriesOptions: { revenue: { type: "line", name: "Revenue (net)", color: "#ff0000", yAxis: 1 } } })
      );
      const [built0] = built.option.series;

      expect(built0.type).toBe("line");
      expect(built0.name).toBe("Revenue (net)");
      expect(built0.itemStyle.color).toBe("#ff0000");
      expect(built0.yAxisIndex).toBe(1);
      // The id stays keyed to the query's series name, not the display name,
      // so renaming a series in the editor does not break its animation.
      expect(built0.id).toBe("series:revenue");
    });

    test("stacking groups the series", () => {
      const built = buildOption(
        [series("a", [["x", 1]]), series("b", [["x", 2]])],
        options({ series: { stacking: "stack" } })
      );

      expect(built.option.series[0].stack).toBe("total");
      expect(built.option.series[1].stack).toBe("total");
    });

    test("column charts become bars, area charts become filled lines", () => {
      const column = buildOption([series("a", [["x", 1]])], options({ globalSeriesType: "column" }));
      const area = buildOption([series("a", [["x", 1]])], options({ globalSeriesType: "area" }));

      expect(column.option.series[0].type).toBe("bar");
      expect(area.option.series[0].type).toBe("line");
      expect(area.option.series[0].areaStyle).toBeTruthy();
    });

    test("swapped axes put the categories on the y axis", () => {
      const built = buildOption([series("a", [["x", 1]])], options({ swappedAxes: true }));

      expect(built.option.yAxis[0].type).toBe("category");
      // Two measure axes either way round, so a series assigned to the second
      // one still has an axis to sit on.
      expect(built.option.xAxis[0].type).toBe("value");
    });

    test("data labels animate their value rather than snapping", () => {
      const built = buildOption([series("a", [["x", 1]])], options({ showDataLabels: true }));

      expect(built.option.series[0].label.show).toBe(true);
      expect(built.option.series[0].label.valueAnimation).toBe(true);
    });

    test("the legend follows the saved setting", () => {
      const shown = buildOption([series("a", [["x", 1]])], options({ legend: { enabled: true } }));
      const hidden = buildOption([series("a", [["x", 1]])], options({ legend: { enabled: false } }));

      expect(shown.option.legend.show).toBe(true);
      expect(hidden.option.legend.show).toBe(false);
    });
  });

  describe("pie", () => {
    test("builds one slice per point", () => {
      const built = buildOption(
        [
          series("sales", [
            ["a", 1],
            ["b", 2],
          ]),
        ],
        options({ globalSeriesType: "pie" })
      );
      const [pie] = built.option.series;

      expect(pie.type).toBe("pie");
      expect(pie.data.map((d: any) => [d.name, d.value])).toEqual([
        ["a", 1],
        ["b", 2],
      ]);
      expect(built.option.xAxis).toBeUndefined();
    });
  });

  describe("an automatic x axis", () => {
    const at = (iso: string) => moment.utc(iso);

    test("times get a time axis, not a number line from 1970", () => {
      // A datetime column arrives as moments, and a moment is also a number
      // (its epoch milliseconds): checked the other way round, every time
      // series was drawn as a spike at the right-hand end of 0 to 1.8e12.
      const line = {
        ...series("rps", [
          [at("2026-09-19T20:50:00Z"), 300],
          [at("2026-09-19T20:51:00Z"), 320],
        ]),
        type: "line",
      };
      const built = buildOption(
        [line],
        options({ globalSeriesType: "line", xAxis: { type: "-", labels: { enabled: true } } })
      );

      expect(built.option.xAxis.type).toBe("time");
      expect(built.option.series[0].data[0][0]).toBe(Date.parse("2026-09-19T20:50:00Z"));
      // ...and ECharts labels it as times, not as "1789852380000".
      expect(built.option.xAxis.axisLabel.formatter).toBeUndefined();
    });

    test("ISO dates in text columns count as times too", () => {
      expect(echartsAxisType("-", ["2026-09-19 20:50:00", "2026-09-19T20:51:00+00:00", "2026-09-20"])).toBe("time");
    });

    test("numbers, and numbers in text, still get a value axis", () => {
      expect(echartsAxisType("-", [1, 2, 3])).toBe("value");
      expect(echartsAxisType("-", ["1", "2.5"])).toBe("value");
      expect(echartsAxisType("-", [2024, 2025])).toBe("value");
    });

    test("anything mixed is categories", () => {
      expect(echartsAxisType("-", ["2026-09-19", "North"])).toBe("category");
      expect(echartsAxisType("-", [])).toBe("category");
    });
  });

  describe("legend placement", () => {
    const two = () => [series("revenue", [["a", 1]]), series("cost", [["a", 2]])];

    test("Right puts it down the right side, and the plot makes room for it", () => {
      const built = buildOption(two(), options({ legend: { enabled: true, placement: "auto" } }));
      expect(built.option.legend.orient).toBe("vertical");
      expect(built.option.legend.right).toBeDefined();
      expect(built.option.legend.bottom).toBeUndefined();
      expect(built.option.grid.right).toBeGreaterThan(36);
      expect(built.option.grid.bottom).toBeLessThan(36);
    });

    test("Below puts it under the chart", () => {
      const built = buildOption(two(), options({ legend: { enabled: true, placement: "below" } }));
      expect(built.option.legend.bottom).toBe(0);
      expect(built.option.legend.orient).toBeUndefined();
      expect(built.option.grid.bottom).toBeGreaterThanOrEqual(36);
    });

    test("a short chart carries fewer y labels, a tall one is left alone", () => {
      // Only ever takes labels away. Five is what ECharts asks for anyway, so
      // anything tall enough is unchanged; a two-row widget stops stacking
      // six labels a dozen pixels apart.
      expect(valueAxisSplitNumber(0)).toBeUndefined();
      expect(valueAxisSplitNumber(60)).toBe(2);
      expect(valueAxisSplitNumber(130)).toBe(2);
      expect(valueAxisSplitNumber(176)).toBe(3);
      expect(valueAxisSplitNumber(280)).toBe(5);
      expect(valueAxisSplitNumber(900)).toBe(5);
      [0, 40, 100, 200, 400, 1200].forEach((h) => {
        const n = valueAxisSplitNumber(h);
        expect(n === undefined || n <= 5).toBe(true);
      });
    });

    test("an unmeasured chart is left entirely to ECharts", () => {
      const built = buildOption(two(), options({}));
      expect(built.option.yAxis[0].splitNumber).toBeUndefined();
    });

    test("a measured, short chart asks for fewer", () => {
      const built = buildOption(two(), options({}), { width: 400, height: 200 });
      expect(built.option.yAxis[0].splitNumber).toBe(3);
      expect(built.option.yAxis[0].axisLabel.hideOverlap).toBe(true);
    });

    test("nothing is reserved above the plot, because nothing is drawn there", () => {
      // The legend goes right or below, never on top, so the top of the grid
      // is breathing room and no more. It used to reserve as much as a legend
      // below needs, on every chart, for nothing.
      const built = buildOption(two(), options({ legend: { enabled: true, placement: "below" } }));
      expect(built.option.grid.top).toBeLessThan(built.option.grid.bottom);
      expect(built.option.grid.top).toBeLessThanOrEqual(16);
    });

    test("very long names are cut short rather than squeezing the plot away", () => {
      const long = [series("x".repeat(200), [["a", 1]])];
      const built = buildOption(long, options({ legend: { enabled: true, placement: "auto" } }));
      expect(built.option.grid.right).toBeLessThanOrEqual(180);
      expect(built.option.legend.textStyle.overflow).toBe("truncate");
    });

    test("a pie moves left of a legend on the right", () => {
      const pie = [
        {
          ...series("share", [
            ["a", 1],
            ["b", 2],
          ]),
          type: "pie",
        },
      ];
      const right = buildOption(
        pie,
        options({ globalSeriesType: "pie", legend: { enabled: true, placement: "auto" } })
      );
      const below = buildOption(
        pie,
        options({ globalSeriesType: "pie", legend: { enabled: true, placement: "below" } })
      );
      expect(parseFloat(right.option.series[0].center[0])).toBeLessThan(50);
      expect(below.option.series[0].center[0]).toBe("50%");
    });
  });

  describe("reading a value under the pointer", () => {
    const item = (x: string, y: number, name = "revenue") => ({
      axisValueLabel: x,
      name: x,
      seriesName: name,
      marker: "",
      value: [x, y],
    });

    test("the x value heads the tooltip, above each series' number", () => {
      const built = buildOption([series("revenue", [["March", 2100]])], options());
      const html = built.option.tooltip.formatter([item("March", 2100)]);

      expect(html.indexOf("March")).toBeGreaterThanOrEqual(0);
      expect(html.indexOf("March")).toBeLessThan(html.indexOf("revenue"));
    });

    test("a category from the data cannot inject markup into the tooltip", () => {
      const built = buildOption([series("revenue", [["<b>x</b>", 1]])], options());
      const html = built.option.tooltip.formatter([item("<b>x</b>", 1)]);

      expect(html).toContain("&lt;b&gt;x&lt;/b&gt;");
    });

    test("the x value is labelled on the axis under the pointer, for bars, lines and points", () => {
      ["column", "line", "area", "scatter"].forEach((type) => {
        const built = buildOption([{ ...series("revenue", [["a", 1]]), type }], options({ globalSeriesType: type }));
        expect(built.option.tooltip.axisPointer.label.show).toBe(true);
      });
    });
  });

  describe("animation defaults", () => {
    test("updates are animated out of the box", () => {
      const built = buildOption([series("a", [["x", 1]])], options());

      expect(built.option.animation).toBe(true);
      expect(built.option.animationDurationUpdate).toBeGreaterThan(0);
      expect(built.option.animationEasingUpdate).toBe("cubicInOut");
    });

    test("slow enough to see: a first draw and a change each take about a second", () => {
      // 300 and 450 ms were over before anyone watching a dashboard noticed.
      const built = buildOption([series("a", [["x", 1]])], options());

      expect(built.option.animationDuration).toBeGreaterThanOrEqual(900);
      expect(built.option.animationDurationUpdate).toBeGreaterThanOrEqual(900);
    });
  });
});
