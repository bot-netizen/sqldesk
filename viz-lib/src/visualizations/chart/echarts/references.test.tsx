import React from "react";
import enzyme from "enzyme";
import moment from "moment";
import getOptions from "../getOptions";
import buildOption from "./buildOption";
import { applyWindow } from "./references";
import { TabbedEditor } from "@/components/visualizations/editor/createTabbedEditor";
import ReferenceSettings from "../Editor/ReferenceSettings";

// eslint-disable-next-line @typescript-eslint/no-var-requires
const echarts = require("echarts");

function series(name: string, points: [any, number][]) {
  return { name, data: points.map(([x, y]) => ({ x, y })) };
}

const cats = [
  series("orders", [
    ["a", 1],
    ["b", 2],
    ["c", 3],
    ["d", 4],
  ]),
];

function build(extra: any, data: any[] = cats) {
  return buildOption(data, getOptions({ globalSeriesType: "line", ...extra })).option;
}

function reference(option: any) {
  return option.series.find((s: any) => s.id === "series:reference");
}

describe("Visualizations -> Chart -> rolling window", () => {
  test("off by default: every point", () => {
    expect(applyWindow(cats, undefined)).toBe(cats);
  });

  test("the last few points, in the query's order for categories", () => {
    const out = applyWindow(cats, { mode: "points", points: 2 });
    expect(out[0].data.map((p: any) => p.x)).toEqual(["c", "d"]);
  });

  test("the last few points, chronologically for times, and series stay aligned", () => {
    const t = (m: number) => moment.utc("2026-09-18T10:00:00Z").add(m, "minutes");
    const data = [
      series("a", [
        [t(2), 1],
        [t(0), 2],
        [t(1), 3],
      ]),
      series("b", [
        [t(1), 5],
        [t(2), 6],
      ]),
    ];
    const out = applyWindow(data, { mode: "points", points: 2 });
    expect(out[0].data.map((p: any) => p.y)).toEqual([1, 3]);
    expect(out[1].data.map((p: any) => p.y)).toEqual([5, 6]);
  });

  test("the last few minutes before the latest point", () => {
    const data = [
      series("a", [
        ["2026-09-18 10:00:00", 1],
        ["2026-09-18 10:50:00", 2],
        ["2026-09-18 11:00:00", 3],
      ]),
    ];
    expect(applyWindow(data, { mode: "minutes", minutes: 15 })[0].data.map((p: any) => p.y)).toEqual([2, 3]);
  });

  test("minutes do nothing on an axis that is not time", () => {
    expect(applyWindow(cats, { mode: "minutes", minutes: 5 })).toBe(cats);
  });

  test("the window is applied before categories are worked out", () => {
    const option = build({ window: { mode: "points", points: 2 } });
    expect(option.xAxis.data).toEqual(["c", "d"]);
  });
});

describe("Visualizations -> Chart -> reference lines and bands", () => {
  test("none by default, and no extra series", () => {
    expect(reference(build({}))).toBeUndefined();
  });

  test("a line at a value rides on its own series", () => {
    const option = build({
      referenceLines: [{ kind: "value", value: 3, label: "Goal", color: "good", style: "solid" }],
    });
    const line = reference(option).markLine.data[0];
    expect(line.yAxis).toBe(3);
    expect(line.label.formatter).toBe("Goal");
    expect(line.lineStyle).toEqual({ color: "#1e7a4c", type: "solid", width: 1.5 });
    // The legend lists the data series only.
    expect(option.legend.data).toEqual(["orders"]);
  });

  test("sideways, a value line is on the x axis", () => {
    const option = build({
      swappedAxes: true,
      globalSeriesType: "column",
      referenceLines: [{ kind: "value", value: 3 }],
    });
    expect(reference(option).markLine.data[0].xAxis).toBe(3);
  });

  test("statistics are ECharts' own, on the series they describe", () => {
    const option = build({ referenceLines: [{ kind: "average", label: "", color: "accent" }] });
    const orders = option.series.find((s: any) => s.name === "orders");
    expect(orders.markLine.data[0].type).toBe("average");
    expect(orders.markLine.data[0].label.formatter).toBe("Average {c}");
  });

  test("a marker along the x axis", () => {
    const option = build({ referenceLines: [{ kind: "x", value: "c", label: "Launch" }] });
    expect(reference(option).markLine.data[0].xAxis).toBe("c");
  });

  test("an unusable line is skipped rather than drawn at zero", () => {
    expect(reference(build({ referenceLines: [{ kind: "value", value: null }] }))).toBeUndefined();
  });

  test("bands run to the edge of the axis when an end is left empty", () => {
    const option = build({ referenceBands: [{ from: 2, to: null, label: "High", color: "warning" }] });
    const [start, end] = reference(option).markArea.data[0];
    expect(start.yAxis).toBe(2);
    expect(end.yAxis).toBe("max");
    expect(start.name).toBe("High");
  });

  test("they draw", () => {
    const chart = echarts.init(null, null, { renderer: "svg", ssr: true, width: 480, height: 300 });
    try {
      chart.setOption(
        build({
          referenceLines: [{ kind: "value", value: 3, label: "Goal line" }],
          referenceBands: [{ from: 1, to: 2, label: "Normal band", color: "good" }],
        })
      );
      const svg = chart.renderToSVGString();
      expect(svg).toContain("Goal line");
      expect(svg).toContain("Normal band");
    } finally {
      chart.dispose();
    }
  });
});

describe("Visualizations -> Chart -> zoom", () => {
  test("off by default", () => {
    expect(build({}).dataZoom).toBeUndefined();
  });

  test("a slider on the category axis, with room made for it", () => {
    const plain = build({});
    const zoomed = build({ zoom: "slider" });
    expect(zoomed.dataZoom).toEqual([expect.objectContaining({ type: "slider", xAxisIndex: 0 })]);
    expect(zoomed.grid.bottom).toBe(plain.grid.bottom + 30);
  });

  test("the wheel and dragging, sideways", () => {
    const option = build({ zoom: "inside", swappedAxes: true, globalSeriesType: "column" });
    expect(option.dataZoom).toEqual([expect.objectContaining({ type: "inside", yAxisIndex: 0 })]);
  });
});

describe("Visualizations -> Chart -> Lines & Zoom editor", () => {
  test("removing a line removes it, through the real tabbed editor", () => {
    let options: any = getOptions({
      globalSeriesType: "line",
      referenceLines: [
        { kind: "value", value: 1, label: "a" },
        { kind: "value", value: 2, label: "b" },
      ],
    });
    const onOptionsChange = jest.fn((next: any) => {
      options = next;
    });
    const w = enzyme.mount(
      <TabbedEditor
        tabs={[{ key: "References", title: "Lines", component: ReferenceSettings }] as any}
        {...({ options, data: { columns: [], rows: [] }, onOptionsChange } as any)}
      />
    );
    w.find('[data-test="Chart.Reference.Line.1.Remove"]').last().simulate("click");
    expect(options.referenceLines.map((l: any) => l.label)).toEqual(["a"]);
  });
});
