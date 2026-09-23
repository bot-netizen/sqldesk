import React from "react";
import { mount } from "enzyme";
import { act } from "react-dom/test-utils";
import DashboardGrid from "./DashboardGrid";

// The real enum's module pulls in every chart type.
jest.mock("@/services/widget", () => ({
  WidgetTypeEnum: { TEXTBOX: "textbox", VISUALIZATION: "visualization", RESTRICTED: "restricted" },
}));

// Every `getDashboard` a widget is handed, in render order, so a test can ask
// what it returns and whether it kept its identity.
const mockHandedGetters = [];

// Stand-ins that draw only what matters here: the id of the result shown.
jest.mock("@/components/dashboards/dashboard-widget", () => {
  // eslint-disable-next-line global-require
  const MockReact = require("react");
  return {
    VisualizationWidget: ({ widget, getDashboard }) => {
      mockHandedGetters.push(getDashboard);
      return MockReact.createElement("span", { className: "shown" }, String(widget.getQueryResult().id));
    },
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
  beforeEach(() => {
    mockHandedGetters.length = 0;
  });

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

  test("a widget reads the dashboard when it needs it, not when it last rendered", () => {
    // The dialog a widget opens needs the dashboard as it is at that moment.
    // The widget is memoized on everything except `dashboard` -- deliberately,
    // since its identity changes on every widget load -- so it can go many
    // renders without seeing a new one. A getter is what bridges that.
    const widget = fakeWidget();
    const dashboard = { id: 1, name: "before", canEdit: () => false };
    const wrapper = mount(<DashboardGrid dashboard={dashboard} widgets={[widget]} isEditing={false} />);

    const later = { id: 1, name: "after", canEdit: () => false };
    act(() => {
      wrapper.setProps({ dashboard: later });
    });
    wrapper.update();

    expect(mockHandedGetters[0]()).toBe(later);
  });

  test("the getter it hands down keeps its identity, so the memo still holds", () => {
    // A fresh arrow per render would make `getDashboard` differ every time and
    // any comparator that looked at it would never match -- the same trap the
    // dashboard object itself was.
    const widget = fakeWidget();
    const dashboard = { id: 1, canEdit: () => false };
    const wrapper = mount(<DashboardGrid dashboard={dashboard} widgets={[widget]} isEditing={false} />);

    // Something that does get the widget re-rendered: a new result.
    widget.data = { id: 2 };
    act(() => {
      wrapper.setProps({ dashboard: { ...dashboard } });
    });
    wrapper.update();

    expect(mockHandedGetters.length).toBeGreaterThan(1);
    expect(new Set(mockHandedGetters).size).toBe(1);
  });
});
