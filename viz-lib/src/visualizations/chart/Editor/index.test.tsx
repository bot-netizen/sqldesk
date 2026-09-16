import React from "react";
import enzyme from "enzyme";

import getOptions from "../getOptions";
import Editor from "./index";

function findByTestID(wrapper: any, testId: any) {
  return wrapper.find(`[data-test="${testId}"]`);
}

function elementExists(wrapper: any, testId: any) {
  return findByTestID(wrapper, testId).length > 0;
}

function mount(options: any, data: any) {
  options = getOptions(options);
  return enzyme.mount(<Editor visualizationName="Test" data={data} options={options} onOptionsChange={() => {}} />);
}

describe("Visualizations -> Chart -> Editor (wrapper)", () => {
  test("Renders generic wrapper", () => {
    const el = mount({ globalSeriesType: "column" }, { columns: [], rows: [] });

    expect(elementExists(el, "VisualizationEditor.Tabs.General")).toBeTruthy();
    expect(elementExists(el, "VisualizationEditor.Tabs.XAxis")).toBeTruthy();
    expect(elementExists(el, "VisualizationEditor.Tabs.YAxis")).toBeTruthy();
    expect(elementExists(el, "VisualizationEditor.Tabs.Series")).toBeTruthy();
    expect(elementExists(el, "VisualizationEditor.Tabs.Colors")).toBeTruthy();
    expect(elementExists(el, "VisualizationEditor.Tabs.DataLabels")).toBeTruthy();

    expect(elementExists(el, "Chart.GlobalSeriesType")).toBeTruthy(); // general settings block exists
    expect(elementExists(el, "Chart.Custom.Code")).toBeFalsy(); // custom settings block does not exist
  });

  test("A chart saved as custom opens as an ordinary chart, not a broken one", () => {
    // Custom charts were Plotly JavaScript and went with Plotly. Opening one
    // should give the author every tab, so they can turn it into a real chart.
    const el = mount({ globalSeriesType: "custom" }, { columns: [], rows: [] });

    expect(elementExists(el, "VisualizationEditor.Tabs.General")).toBeTruthy();
    expect(elementExists(el, "VisualizationEditor.Tabs.XAxis")).toBeTruthy();
    expect(elementExists(el, "VisualizationEditor.Tabs.YAxis")).toBeTruthy();
    expect(elementExists(el, "VisualizationEditor.Tabs.Series")).toBeTruthy();
    expect(elementExists(el, "VisualizationEditor.Tabs.Colors")).toBeTruthy();
    expect(elementExists(el, "VisualizationEditor.Tabs.DataLabels")).toBeTruthy();

    expect(elementExists(el, "Chart.Custom.Code")).toBeFalsy(); // the code editor is gone
  });
});
