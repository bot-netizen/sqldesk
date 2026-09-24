import React from "react";
import { mount } from "enzyme";
import QueryLink from "./QueryLink";

jest.mock("@sqldesk/viz/lib", () => ({
  // eslint-disable-next-line global-require
  VisualizationType: require("prop-types").object,
  registeredVisualizations: { CHART: { name: "Chart" } },
}));

const query = (name) => ({ name, getUrl: () => "/queries/7" });
const visualization = (name) => ({ id: 1, type: "CHART", name, options: {} });

/*
  A dashboard of five widgets over one query used to carry that query's name
  five times. The title is one name now, and which one depends on whether the
  visualization has one worth saying.
*/

describe("a widget's title", () => {
  test("is the visualization's name when it has one of its own", () => {
    const wrapper = mount(<QueryLink query={query("Revenue")} visualization={visualization("By region")} />);

    expect(wrapper.text()).toBe("By region");
    expect(wrapper.text()).not.toContain("Revenue");
  });

  test("is the query's name when the visualization has none", () => {
    // "Chart" is the type's default, which says nothing the tile does not.
    expect(mount(<QueryLink query={query("Revenue")} visualization={visualization("Chart")} />).text()).toBe("Revenue");
  });

  test("is the query's name when the visualization only repeats it", () => {
    const wrapper = mount(<QueryLink query={query("Revenue")} visualization={visualization("Revenue")} />);
    expect(wrapper.text()).toBe("Revenue");
  });

  test("and with no visualization at all", () => {
    expect(mount(<QueryLink query={query("Revenue")} />).text()).toBe("Revenue");
  });

  test("names the query on the link, so nothing is actually lost", () => {
    const wrapper = mount(<QueryLink query={query("Revenue")} visualization={visualization("By region")} />);
    expect(wrapper.find("a").prop("title")).toBe("Revenue");
  });

  test("does not repeat the query's name in the tooltip when it is the title", () => {
    const wrapper = mount(<QueryLink query={query("Revenue")} visualization={visualization("Chart")} />);
    expect(wrapper.find("a").prop("title")).toBeNull();
  });

  test("still links to the query, and to the visualization within it", () => {
    const linked = { name: "Revenue", getUrl: jest.fn(() => "/queries/7#1") };
    mount(<QueryLink query={linked} visualization={visualization("By region")} />);
    expect(linked.getUrl).toHaveBeenCalledWith(false, 1);
  });

  test("a table links to the table tab, which has no visualization id", () => {
    const linked = { name: "Revenue", getUrl: jest.fn(() => "/queries/7#table") };
    mount(<QueryLink query={linked} visualization={{ id: 2, type: "TABLE", name: "Rows", options: {} }} />);
    expect(linked.getUrl).toHaveBeenCalledWith(false, "table");
  });

  test("read-only is a span, not a link", () => {
    const wrapper = mount(<QueryLink query={query("Revenue")} visualization={visualization("By region")} readOnly />);
    expect(wrapper.find("a")).toHaveLength(0);
    expect(wrapper.text()).toBe("By region");
  });
});
