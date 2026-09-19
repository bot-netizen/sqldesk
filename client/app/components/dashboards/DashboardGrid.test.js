import React from "react";
import { mount } from "enzyme";
import { act } from "react-dom/test-utils";
import DashboardGrid from "./DashboardGrid";

// The real enum's module pulls in every chart type.
jest.mock("@/services/widget", () => ({
  WidgetTypeEnum: { TEXTBOX: "textbox", VISUALIZATION: "visualization", RESTRICTED: "restricted" },
}));

// Stand-ins that draw only what matters here: the id of the result shown.
jest.mock("@/components/dashboards/dashboard-widget", () => {
  // eslint-disable-next-line global-require
  const MockReact = require("react");
  return {
    VisualizationWidget: ({ widget }) =>
      MockReact.createElement("span", { className: "shown" }, String(widget.getQueryResult().id)),
    TextboxWidget: () => null,
    RestrictedWidget: () => null,
  };
});

function fakeWidget() {
  const widget = {
    id: 7,
    type: "visualization",
    visualization: { id: 1 },
    options: { position: { col: 0, row: 0, sizeX: 3, sizeY: 8, autoHeight: false } },
    loading: false,
    data: { id: 1 },
  };
  widget.getQueryResult = () => widget.data;
  return widget;
}

describe("DashboardGrid", () => {
  test("draws a widget's new result even when nothing else about it changed", () => {
    // What a live dashboard's reload does: the same widget object, a new
    // result in it, and a re-render of the page with nothing else different --
    // not loading before, not loading after.
    const widget = fakeWidget();
    const dashboard = { id: 1, canEdit: () => false };
    const wrapper = mount(<DashboardGrid dashboard={dashboard} widgets={[widget]} isEditing={false} />);
    expect(wrapper.find(".shown").text()).toBe("1");

    widget.data = { id: 2 };
    act(() => {
      wrapper.setProps({ dashboard: { ...dashboard } });
    });
    wrapper.update();

    expect(wrapper.find(".shown").text()).toBe("2");
  });
});
