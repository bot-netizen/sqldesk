import React from "react";
import { mount } from "enzyme";

import Catalog, { DESCRIPTION_SHAPE } from "./Catalog";
import { axios } from "@/services/axios";

/*
  The catalog page, where a person writes what each table is for.

  It is sent the first 200 tables by usage. Until 0.7.3 that was all it could
  show: the limit was on the server, so a table past it was unreachable rather
  than merely off-screen. These pin the parts that make a long catalog
  workable -- search over everything, hiding the noise, and saying plainly when
  there is more than the page holds.
*/
const TABLES = [
  { id: 1, name: "orders", usage_count: 40, column_count: 6, description: null, hidden: false },
  { id: 2, name: "refunds", usage_count: 9, column_count: 4, description: "One row per refund.", hidden: false },
];

function server({ tables = TABLES, total = TABLES.length, hidden = 0 } = {}) {
  return jest.spyOn(axios, "get").mockImplementation((url) => {
    if (url.startsWith("/api/catalog?") || url === "/api/catalog") {
      return Promise.resolve({ tables, total, limit: 200, hidden_count: hidden });
    }
    if (url === "/api/catalog/sources") {
      return Promise.resolve({ sources: [] });
    }
    if (url === "api/data_sources") {
      return Promise.resolve([]);
    }
    return Promise.resolve({});
  });
}

async function settle(wrapper, times = 4) {
  for (let index = 0; index < times; index += 1) {
    // eslint-disable-next-line no-await-in-loop
    await new Promise((resolve) => setTimeout(resolve, 0));
    wrapper.update();
  }
}

function catalogCalls(get) {
  return get.mock.calls.map(([url]) => url).filter((url) => url.startsWith("/api/catalog?") || url === "/api/catalog");
}

describe("the catalog page", () => {
  afterEach(() => {
    jest.restoreAllMocks();
    jest.useRealTimers();
  });

  test("a search is asked of the server, so it reaches tables the page was not sent", async () => {
    jest.useFakeTimers();
    const get = server();
    const wrapper = mount(<Catalog />);
    jest.runOnlyPendingTimers();
    await Promise.resolve();

    wrapper.find('input[data-test="CatalogSearch"]').simulate("change", { target: { value: "nobody_could_see" } });
    // A pause, not a keystroke, is a request.
    jest.advanceTimersByTime(350);
    await Promise.resolve();

    expect(catalogCalls(get).some((url) => url.includes("q=nobody_could_see"))).toBe(true);
  });

  test("it says when there are more tables than it was sent", async () => {
    server({ total: 1432 });
    const wrapper = mount(<Catalog />);
    await settle(wrapper);

    const said = wrapper.find('[data-test="CatalogTruncated"]').first().text();
    expect(said).toContain("1,432");
    expect(said).toContain("Search to find any of them");
  });

  test("and says nothing of the kind when it has them all", async () => {
    server();
    const wrapper = mount(<Catalog />);
    await settle(wrapper);

    expect(wrapper.find('[data-test="CatalogTruncated"]').exists()).toBe(false);
  });

  test("hiding a table tells the server and takes it off the page", async () => {
    server();
    const post = jest.spyOn(axios, "post").mockResolvedValue({ id: 1, hidden: true });
    const wrapper = mount(<Catalog />);
    await settle(wrapper);

    wrapper.find('input[aria-label="Hide orders"]').simulate("change", { target: { checked: true } });
    await settle(wrapper, 2);

    expect(post).toHaveBeenCalledWith("/api/catalog/tables/1", { hidden: true });
    expect(wrapper.text()).not.toContain("orders");
  });

  test("showing hidden tables asks for them, and says how many there are", async () => {
    const get = server({ hidden: 37 });
    const wrapper = mount(<Catalog />);
    await settle(wrapper);

    expect(wrapper.text()).toContain("Show hidden (37)");
    wrapper.find('button[data-test="ShowHidden"]').simulate("click");
    await settle(wrapper, 2);

    expect(catalogCalls(get).some((url) => url.includes("hidden=1"))).toBe(true);
  });

  test("the described filter asks for only the ones with a description", async () => {
    const get = server();
    const wrapper = mount(<Catalog />);
    await settle(wrapper);

    wrapper.find('input[value="described"]').simulate("change", { target: { checked: true } });
    await settle(wrapper, 2);

    expect(catalogCalls(get).some((url) => url.includes("described=1") && !url.includes("undescribed"))).toBe(true);
  });

  test("a description written through MCP says so", async () => {
    server({
      tables: [
        { id: 3, name: "events", column_count: 2, description: "One row per event.", description_source: "mcp" },
      ],
    });
    const wrapper = mount(<Catalog />);
    await settle(wrapper);

    expect(wrapper.text()).toContain("via MCP");
  });

  test("and says whose key wrote it", async () => {
    // "via MCP" says a machine typed the sentence. The first question about a
    // wrong one is whose machine.
    server({
      tables: [
        {
          id: 3,
          name: "events",
          column_count: 2,
          description: "One row per event.",
          description_source: "mcp",
          described_by: "Iqbal",
        },
      ],
    });
    const wrapper = mount(<Catalog />);
    await settle(wrapper);

    expect(wrapper.text()).toContain("Iqbal");
  });

  test("the agent filter asks the server for exactly what an agent wrote", async () => {
    const get = server();
    const wrapper = mount(<Catalog />);
    await settle(wrapper);

    wrapper.find('input[value="mcp"]').simulate("change", { target: { checked: true } });
    await settle(wrapper, 2);

    expect(catalogCalls(get).some((url) => url.includes("source=mcp"))).toBe(true);
  });

  test("an empty description shows the shape a good one takes", async () => {
    server();
    const wrapper = mount(<Catalog />);
    await settle(wrapper);

    const placeholder = wrapper.find('textarea[data-test="TableDescription"]').first().prop("placeholder");
    expect(placeholder).toBe(DESCRIPTION_SHAPE);
    expect(placeholder).toContain("Partitioned by");
    expect(placeholder).toContain("Key:");
  });
});
