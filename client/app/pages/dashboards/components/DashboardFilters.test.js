import React from "react";
import { mount } from "enzyme";
import DashboardFilters from "./DashboardFilters";

jest.mock("@/components/Parameters", () => () => <div data-test="MockParameters" />);
jest.mock("@/components/Filters", () => () => <div data-test="MockFilters" />);

const param = (name) => ({ name, title: name, type: "text", value: "" });

function config(over = {}) {
  return {
    globalParameters: [],
    filters: [],
    refreshDashboard: () => {},
    setFilters: () => {},
    live: null,
    ...over,
  };
}

const render = (over) => mount(<DashboardFilters dashboardConfiguration={config(over)} />);
const hasButton = (w) => w.find('[data-test="DashboardFiltersButton"]').length > 0;
const count = (w) => w.find(".ant-badge").text();

/*
  The filters used to get a full-width band above the grid -- 93px plus its
  margin for a single dropdown. In the header they cost one button, and it is
  the same one button however many filters are behind it: a dashboard that
  gains a fourth parameter should not rearrange its own header.
*/

describe("where a dashboard's filters go", () => {
  test("nothing at all when there is nothing to filter by", () => {
    expect(render().html()).toBeNull();
  });

  test("one parameter is already a button, not a control in the header", () => {
    expect(hasButton(render({ globalParameters: [param("a")] }))).toBe(true);
  });

  test("and so are four, in the same place", () => {
    const w = render({ globalParameters: [param("a"), param("b"), param("c"), param("d")] });
    expect(hasButton(w)).toBe(true);
    expect(count(w)).toContain("4");
  });

  test("the button counts column filters too", () => {
    const w = render({ globalParameters: [param("a")], filters: [{ name: "region", values: [] }] });
    expect(count(w)).toContain("2");
  });

  test("a live dashboard offers no parameter controls at all", () => {
    // The server refreshes it from the saved values, so a control that
    // changed nothing would be a lie.
    expect(render({ globalParameters: [param("a")], live: { interval: 30 } }).html()).toBeNull();
  });

  test("but a live dashboard's column filters still work, since they filter rows in the browser", () => {
    expect(hasButton(render({ live: { interval: 30 }, filters: [{ name: "region", values: [] }] }))).toBe(true);
  });
});
