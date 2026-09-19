import React from "react";
import { mount } from "enzyme";
import VisualizationName from "./VisualizationName";

jest.mock("@sqldesk/viz/lib", () => ({
  // eslint-disable-next-line global-require
  VisualizationType: require("prop-types").object,
  registeredVisualizations: { CHART: { name: "Chart" } },
}));

const named = (name) => ({ id: 1, type: "CHART", name, options: {} });

describe("VisualizationName", () => {
  test("a name of its own is shown", () => {
    expect(mount(<VisualizationName visualization={named("By region")} queryName="Revenue" />).text()).toBe(
      "By region"
    );
  });

  test("the type's default name is not", () => {
    expect(mount(<VisualizationName visualization={named("Chart")} queryName="Revenue" />).text()).toBe("");
  });

  test("nor the query's own name again", () => {
    // "Requests per second - Requests per second" said nothing twice.
    expect(
      mount(<VisualizationName visualization={named("Requests per second")} queryName="Requests per second" />).text()
    ).toBe("");
  });
});
