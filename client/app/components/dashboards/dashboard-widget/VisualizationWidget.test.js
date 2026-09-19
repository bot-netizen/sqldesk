import React from "react";
import { shallow } from "enzyme";
import VisualizationWidget from "./VisualizationWidget";
import Widget from "./Widget";

jest.mock("@/services/auth", () => ({ currentUser: { hasPermission: () => false } }));
jest.mock("@/services/recordEvent", () => jest.fn());
// Charts are not what is under test, and pull in ECharts' ESM build.
jest.mock("@/components/visualizations/VisualizationRenderer", () => () => null);
jest.mock("@/components/QueryLink", () => () => null);
jest.mock("@/components/dashboards/ExpandedWidgetDialog", () => ({}));
jest.mock("@/components/dashboards/EditParameterMappingsDialog", () => ({}));

function fakeWidget() {
  return {
    id: 1,
    options: {},
    visualization: { id: 2, query: { id: 3 } },
    getLocalParameters: () => [{ name: "n", title: "n", type: "number" }],
    getQueryResult: () => null,
    getQuery: () => ({ id: 3, name: "Query", description: "", getUrl: () => "/queries/3" }),
  };
}

describe("VisualizationWidget", () => {
  test("its own parameters and its Refresh button go to separate handlers", () => {
    const onRefresh = jest.fn();
    const onParametersChange = jest.fn();
    const wrapper = shallow(
      <VisualizationWidget
        widget={fakeWidget()}
        dashboard={{}}
        onRefresh={onRefresh}
        onParametersChange={onParametersChange}
      />
    );
    const { header, footer } = wrapper.find(Widget).props();

    header.props.onParametersUpdate();
    expect(onParametersChange).toHaveBeenCalledTimes(1);
    expect(onRefresh).not.toHaveBeenCalled();

    expect(footer.props.onRefresh).toBe(onRefresh);
  });

  test("a live dashboard's widget offers no parameters to change", () => {
    const wrapper = shallow(<VisualizationWidget widget={fakeWidget()} dashboard={{}} isLive />);
    expect(wrapper.find(Widget).prop("header").props.parameters).toEqual([]);
  });
});
