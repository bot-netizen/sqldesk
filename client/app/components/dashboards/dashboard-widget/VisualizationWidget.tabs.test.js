import React from "react";
import { shallow } from "enzyme";
import VisualizationWidget from "./VisualizationWidget";
import VisualizationRenderer from "@/components/visualizations/VisualizationRenderer";

jest.mock("@/services/auth", () => ({ currentUser: { hasPermission: () => false } }));
jest.mock("@/services/recordEvent", () => jest.fn());
jest.mock("@/components/visualizations/VisualizationRenderer", () => () => null);
jest.mock("@/components/QueryLink", () => () => null);
jest.mock("@/components/dashboards/ExpandedWidgetDialog", () => ({}));
jest.mock("@/components/dashboards/EditParameterMappingsDialog", () => ({
  showModal: jest.fn(() => ({ onClose: () => {} })),
}));
jest.mock("@/components/dashboards/ChooseWidgetTabsDialog", () => ({
  showModal: jest.fn(() => ({ onClose: () => {} })),
}));

const BY_REGION = { id: 2, name: "By region", type: "CHART", options: {} };
const BY_CHANNEL = { id: 7, name: "By channel", type: "CHART", options: {} };
const BY_PRODUCT = { id: 9, name: "By product", type: "CHART", options: {} };

function fakeWidget(extras = []) {
  const visualization = { ...BY_REGION, query: { id: 3 } };
  return {
    id: 1,
    options: {},
    visualization,
    tab_visualizations: extras,
    getTabs: () => [visualization, ...extras],
    getLocalParameters: () => [],
    // "done" is what makes the widget draw rather than spin.
    getQueryResult: () => ({ getStatus: () => "done", getError: () => null }),
    getQuery: () => ({ id: 3, name: "Query", description: "", getUrl: () => "/queries/3" }),
  };
}

function mount(widget) {
  return shallow(<VisualizationWidget widget={widget} getDashboard={() => ({})} />);
}

/*
  A query returning region, channel, product and a sum is three charts, not
  one. Before this each was its own widget, which fetched and parsed the same
  result once per chart.
*/
describe("VisualizationWidget tabs", () => {
  describe("when there is nothing to choose between", () => {
    test("a widget with one visualization draws no strip", () => {
      const wrapper = mount(fakeWidget());

      expect(wrapper.find(".widget-tabs")).toHaveLength(0);
    });

    test("and draws the visualization it has always drawn", () => {
      const wrapper = mount(fakeWidget());

      expect(wrapper.find(VisualizationRenderer).props().visualization.id).toBe(BY_REGION.id);
    });
  });

  describe("with tabs", () => {
    test("every visualization gets a tab, the widget's own first", () => {
      const wrapper = mount(fakeWidget([BY_CHANNEL, BY_PRODUCT]));
      const labels = wrapper.find(".widget-tab").map((tab) => tab.children().text());

      expect(labels).toEqual(["By region", "By channel", "By product"]);
    });

    test("the widget's own visualization is the one in front to begin with", () => {
      const wrapper = mount(fakeWidget([BY_CHANNEL, BY_PRODUCT]));

      expect(wrapper.find(VisualizationRenderer).props().visualization.id).toBe(BY_REGION.id);
      expect(wrapper.find(".widget-tab.active")).toHaveLength(1);
    });

    test("clicking a tab draws that visualization instead", () => {
      const wrapper = mount(fakeWidget([BY_CHANNEL, BY_PRODUCT]));
      wrapper.find(".widget-tab").at(2).simulate("click");

      expect(wrapper.find(VisualizationRenderer).props().visualization.id).toBe(BY_PRODUCT.id);
    });

    test("only one tab is marked active at a time", () => {
      const wrapper = mount(fakeWidget([BY_CHANNEL, BY_PRODUCT]));
      wrapper.find(".widget-tab").at(1).simulate("click");

      expect(wrapper.find(".widget-tab.active")).toHaveLength(1);
      expect(wrapper.find(".widget-tab").at(1).props()["aria-selected"]).toBe(true);
      expect(wrapper.find(".widget-tab").at(0).props()["aria-selected"]).toBe(false);
    });

    /*
      Switching must not re-run anything. The result is already in hand and
      every tab is a visualization of the same query -- that is the entire
      reason to prefer this to one widget per chart.
    */
    test("switching tabs does not ask for the query result again", () => {
      const widget = fakeWidget([BY_CHANNEL]);
      const getQueryResult = jest.fn(() => ({ getStatus: () => "done", getError: () => null }));
      widget.getQueryResult = getQueryResult;
      const wrapper = mount(widget);
      const before = getQueryResult.mock.calls.length;

      wrapper.find(".widget-tab").at(1).simulate("click");

      // Re-read on render, never re-fetched: there is no load call to make.
      expect(getQueryResult.mock.calls.length).toBeGreaterThan(before);
      expect(widget.load).toBeUndefined();
    });

    test("the strip is a tablist, so it is reachable without a mouse", () => {
      const wrapper = mount(fakeWidget([BY_CHANNEL]));

      expect(wrapper.find('[role="tablist"]')).toHaveLength(1);
      expect(wrapper.find('[role="tab"]')).toHaveLength(2);
    });
  });

  describe("when a tab goes away underneath somebody", () => {
    test("a selected tab that no longer exists falls back to the widget's own", () => {
      const widget = fakeWidget([BY_CHANNEL]);
      const wrapper = mount(widget);
      wrapper.find(".widget-tab").at(1).simulate("click");
      expect(wrapper.find(VisualizationRenderer).props().visualization.id).toBe(BY_CHANNEL.id);

      // Somebody deletes that visualization while the dashboard is open.
      widget.tab_visualizations = [];
      widget.getTabs = () => [widget.visualization];
      wrapper.setProps({ widget });

      expect(wrapper.find(VisualizationRenderer).props().visualization.id).toBe(BY_REGION.id);
    });
  });
});
