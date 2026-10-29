import React from "react";
import enzyme from "enzyme";

import getOptions from "../getOptions";
import YAxisSettings from "./YAxisSettings";
import SeriesSettings from "./SeriesSettings";
import { supportsPanels } from "./PanelSettings";

function findByTestID(wrapper: any, testId: string) {
  return wrapper.find(`[data-test="${testId}"]`);
}

function exists(wrapper: any, testId: string) {
  return findByTestID(wrapper, testId).length > 0;
}

/** The Y-Axis tab, which is where the panel count and the per-panel rows live. */
function mountAxes(options: any, onChange: any = () => {}) {
  return enzyme.mount(
    <YAxisSettings
      visualizationName="Test"
      data={{ columns: [], rows: [] }}
      options={getOptions(options)}
      onOptionsChange={onChange}
    />
  );
}

const ROWS = [
  { x: "a", spend: 1, change: 2 },
  { x: "b", spend: 3, change: 4 },
];

/** The Series tab, which is where a series picks its panel. */
function mountSeries(options: any, onChange: any = () => {}) {
  return enzyme.mount(
    <SeriesSettings
      visualizationName="Test"
      data={{ columns: [{ name: "x" }, { name: "spend" }, { name: "change" }], rows: ROWS }}
      options={getOptions({ columnMapping: { x: "x", spend: "y", change: "y" }, ...options })}
      onOptionsChange={onChange}
    />
  );
}

describe("Visualizations -> Chart -> Editor -> Panels", () => {
  describe("where the control appears at all", () => {
    test("a chart that can be divided offers it", () => {
      expect(supportsPanels(getOptions({ globalSeriesType: "line" }))).toBe(true);
      expect(supportsPanels(getOptions({ globalSeriesType: "column" }))).toBe(true);
      expect(supportsPanels(getOptions({ globalSeriesType: "area" }))).toBe(true);
    });

    /*
      Absent rather than present-and-ignored: a control that writes a setting
      the renderer discards is worse than no control, because the chart then
      disagrees with the editor and neither says why.
    */
    test("the charts the renderer draws as one panel do not offer it", () => {
      expect(supportsPanels(getOptions({ globalSeriesType: "pie" }))).toBe(false);
      expect(supportsPanels(getOptions({ globalSeriesType: "heatmap" }))).toBe(false);
      expect(supportsPanels(getOptions({ globalSeriesType: "box" }))).toBe(false);
      expect(supportsPanels(getOptions({ globalSeriesType: "column", swappedAxes: true }))).toBe(false);
    });

    test("the count is on the axis tab, because it decides how many axes there are", () => {
      expect(exists(mountAxes({ globalSeriesType: "line" }), "Chart.Panels.Count")).toBe(true);
    });

    test("a sideways chart's axis tab has no panel count", () => {
      expect(exists(mountAxes({ globalSeriesType: "column", swappedAxes: true }), "Chart.Panels.Count")).toBe(false);
    });
  });

  describe("choosing how many", () => {
    /*
      Per-panel titles and heights were built and then cut. The tab asks one
      question, and nothing follows from the answer except the column on the
      Series tab.
    */
    test("it asks one question and no more", () => {
      const el = mountAxes({ globalSeriesType: "line", panels: 3 });

      expect(exists(el, "Chart.Panels.0")).toBe(false);
      expect(exists(el, "Chart.Panels.0.Title")).toBe(false);
      expect(exists(el, "Chart.Panels.0.Height")).toBe(false);
    });

    test("every count up to the limit is offered, and nothing past it", () => {
      const el = mountAxes({ globalSeriesType: "line" });
      // antd mounts the options only once the dropdown opens.
      findByTestID(el, "Chart.Panels.Count").last().simulate("mouseDown");

      [1, 2, 3, 4].forEach((n) => expect(exists(el, `Chart.Panels.Count.${n}`)).toBe(true));
      expect(exists(el, "Chart.Panels.Count.5")).toBe(false);
    });

    test("choosing a count writes it", (done) => {
      const el = mountAxes({ globalSeriesType: "line" }, (changed: any) => {
        expect(changed.panels).toBe(3);
        done();
      });

      findByTestID(el, "Chart.Panels.Count").last().simulate("mouseDown");
      findByTestID(el, "Chart.Panels.Count.3").last().simulate("click");
    });

    test("a saved count is what the control shows", () => {
      const el = mountAxes({ globalSeriesType: "line", panels: 3 });

      expect(findByTestID(el, "Chart.Panels.Count").last().props().value).toBe(3);
    });
  });

  describe("a series picking its panel", () => {
    test("no column until there is more than one panel to choose between", () => {
      const el = mountSeries({ globalSeriesType: "line" });

      expect(exists(el, "Chart.Series.spend.Panel")).toBe(false);
    });

    test("two panels give every series the choice", () => {
      const el = mountSeries({ globalSeriesType: "line", panels: 2 });

      expect(exists(el, "Chart.Series.spend.Panel")).toBe(true);
      expect(exists(el, "Chart.Series.change.Panel")).toBe(true);
    });

    test("a sideways chart never asks, whatever is saved", () => {
      const el = mountSeries({ globalSeriesType: "column", swappedAxes: true, panels: 3 });

      expect(exists(el, "Chart.Series.spend.Panel")).toBe(false);
    });

    test("choosing a panel writes it against that series", (done) => {
      const el = mountSeries({ globalSeriesType: "line", panels: 2 }, (changed: any) => {
        expect(changed.seriesOptions.change.panel).toBe(1);
        done();
      });

      findByTestID(el, "Chart.Series.change.Panel").last().simulate("mouseDown");
      findByTestID(el, "Chart.Series.Panel.1").last().simulate("click");
    });

    /*
      Turning the count down leaves a series pointing at a panel that is gone.
      The control has to show where it will actually be drawn, or the editor
      reads back a panel the chart is not using.
    */
    test("a series left pointing at a deleted panel shows the first one", () => {
      const el = mountSeries({
        globalSeriesType: "line",
        panels: 2,
        seriesOptions: { spend: { type: "line", panel: 5 } },
      });

      expect(findByTestID(el, "Chart.Series.spend.Panel").last().props().value).toBe(0);
    });
  });
});
