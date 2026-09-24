import React from "react";
import { mount } from "enzyme";
import DashboardFilters from "./DashboardFilters";

jest.mock("use-media", () => jest.fn(() => true));
jest.mock("@/components/Parameters", () => () => <div data-test="MockParameters" />);
jest.mock("@/components/Filters", () => () => <div data-test="MockFilters" />);

// eslint-disable-next-line global-require
const useMedia = require("use-media");

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
const isInline = (w) => w.find('[data-test="DashboardFilters"]').length > 0;

/*
  The filters used to get a full-width band above the grid -- 93px plus its
  margin for a single dropdown. In the header they cost nothing, as long as
  they never make the header wrap, which is the whole of what is pinned here.
*/

describe("where a dashboard's filters go", () => {
  beforeEach(() => useMedia.mockReturnValue(true));

  test("nothing at all when there is nothing to filter by", () => {
    expect(render().html()).toBeNull();
  });

  test("a few parameters sit in the header", () => {
    const w = render({ globalParameters: [param("a"), param("b"), param("c")] });
    expect(isInline(w)).toBe(true);
    expect(hasButton(w)).toBe(false);
  });

  test("more than a few collapse into a button, so the header cannot wrap", () => {
    const w = render({ globalParameters: [param("a"), param("b"), param("c"), param("d")] });
    expect(hasButton(w)).toBe(true);
    expect(isInline(w)).toBe(false);
  });

  test("the button counts everything behind it", () => {
    const w = render({ globalParameters: [param("a"), param("b"), param("c"), param("d")] });
    expect(w.find(".ant-badge").text()).toContain("4");
  });

  test("a narrow screen always collapses, however few there are", () => {
    useMedia.mockReturnValue(false);
    expect(hasButton(render({ globalParameters: [param("a")] }))).toBe(true);
  });

  test("column filters always collapse, because they are laid out as half-width rows", () => {
    const w = render({ globalParameters: [param("a")], filters: [{ name: "region", values: [] }] });
    expect(hasButton(w)).toBe(true);
    expect(w.find(".ant-badge").text()).toContain("2");
  });

  test("a live dashboard offers no parameter controls at all", () => {
    // The server refreshes it from the saved values, so a control that
    // changed nothing would be a lie.
    const w = render({ globalParameters: [param("a")], live: { interval: 30 } });
    expect(w.html()).toBeNull();
  });

  test("but a live dashboard's column filters still work, since they filter rows in the browser", () => {
    const w = render({ live: { interval: 30 }, filters: [{ name: "region", values: [] }] });
    expect(hasButton(w)).toBe(true);
  });
});
