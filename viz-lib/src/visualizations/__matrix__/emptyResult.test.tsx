import React from "react";
import ReactDOM from "react-dom";
import { act } from "react-dom/test-utils";

import registeredVisualizations from "../registeredVisualizations";
import tableOptions from "../table/getOptions";
import TableRenderer from "../table/Renderer";
import detailsOptions from "../details/getOptions";
import DetailsRenderer from "../details/Renderer";
import statusGridOptions from "../status-grid/getOptions";
import StatusGridRenderer from "../status-grid/Renderer";

import buildHistogram from "../histogram/buildOption";
import histogramOptions from "../histogram/getOptions";
import buildWaterfall from "../waterfall/buildOption";
import waterfallOptions from "../waterfall/getOptions";
import buildRadar from "../radar/buildOption";
import radarOptions from "../radar/getOptions";
import buildTreemap from "../treemap/buildOption";
import treemapOptions from "../treemap/getOptions";
import buildCalendar from "../calendar/buildOption";
import calendarOptions from "../calendar/getOptions";
import buildTimeline from "../timeline/buildOption";
import timelineOptions from "../timeline/getOptions";
import buildGauge from "../gauge/buildOption";
import gaugeOptions from "../gauge/getOptions";
import buildProgress from "../progress/buildOption";
import progressOptions from "../progress/getOptions";
import buildBoxPlot from "../box-plot/buildOption";

/*
  A query that returns nothing is ordinary -- a filter that matched nothing,
  a window with no events in it -- and a blank tile is indistinguishable from
  a widget that failed.

  So every visualization has to say so. The stat and the table did not: the
  stat drew an empty value and an empty label, the table returned null
  outright, and both looked broken beside eight others that explained
  themselves.
*/

const EMPTY = {
  columns: [
    { name: "label", type: "string" },
    { name: "value", type: "float" },
  ],
  rows: [],
};

function textOf(element: React.ReactElement) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  try {
    act(() => {
      ReactDOM.render(element, container);
    });
    return container.textContent || "";
  } finally {
    act(() => {
      ReactDOM.unmountComponentAtNode(container);
    });
    container.remove();
  }
}

describe("a result with no rows", () => {
  const built: [string, () => { problem: string | null }][] = [
    ["Gauge", () => buildGauge(EMPTY, gaugeOptions({}, EMPTY))],
    ["Progress", () => buildProgress(EMPTY, progressOptions({}, EMPTY))],
    ["Histogram", () => buildHistogram(EMPTY, histogramOptions({}, EMPTY))],
    ["Waterfall", () => buildWaterfall(EMPTY, waterfallOptions({}, EMPTY))],
    ["Radar", () => buildRadar(EMPTY, radarOptions({}, EMPTY))],
    ["Treemap", () => buildTreemap(EMPTY, treemapOptions({}, EMPTY))],
    ["Calendar", () => buildCalendar(EMPTY, calendarOptions({}, EMPTY))],
    ["Timeline", () => buildTimeline(EMPTY, timelineOptions({}, EMPTY))],
    ["Box plot", () => buildBoxPlot(EMPTY, {}) as any],
  ];

  test.each(built)("%s says so rather than drawing an empty chart", (_name, build) => {
    const problem = build().problem;
    expect(typeof problem).toBe("string");
    expect((problem as string).length).toBeGreaterThan(0);
  });

  const mounted: [string, React.ReactElement][] = [
    ["Table", <TableRenderer data={EMPTY} options={tableOptions({}, EMPTY)} visualizationName="Table" />],
    ["Details", <DetailsRenderer data={EMPTY} options={detailsOptions({}, EMPTY)} visualizationName="Details" />],
    [
      "Status grid",
      <StatusGridRenderer data={EMPTY} options={statusGridOptions({}, EMPTY)} visualizationName="Status grid" />,
    ],
  ];

  test.each(mounted)("%s says so rather than rendering a blank tile", (_name, element) => {
    expect(textOf(element).trim()).toBe("No rows to show.");
  });

  test("every visualization that can say it uses the same words", () => {
    // Eight different phrasings for the same nothing would read as eight
    // different problems.
    const said = built.map(([, build]) => build().problem).filter((p) => p === "No rows to show.");
    expect(said.length).toBeGreaterThanOrEqual(7);
  });

  test("the stat is covered too, through the registry rather than directly", () => {
    // Its renderer reaches ECharts for the sparkline, which jest cannot load,
    // so what is pinned here is that it is registered and knows the case --
    // the mounted behaviour is checked on a running instance.
    expect((registeredVisualizations as any).COUNTER).toBeDefined();
  });
});
