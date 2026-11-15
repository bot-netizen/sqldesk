jest.mock("@/services/auth", () => ({
  Auth: { getApiKey: () => null, isAuthenticated: () => true },
  clientConfig: {},
  currentUser: { id: 1, name: "Iqbal", profile_image_url: "", hasPermission: () => true, can: () => false },
}));

jest.mock("@/services/axios", () => ({
  axios: {
    get: () => Promise.resolve([]),
    post: () => Promise.resolve({}),
    interceptors: { request: { use: () => {} }, response: { use: () => {} } },
  },
}));

// eslint-disable-next-line import/first
import React from "react";
// eslint-disable-next-line import/first
import { mount } from "enzyme";
// eslint-disable-next-line import/first
import { Query } from "@/services/query";
// eslint-disable-next-line import/first
import QuerySelector from "./QuerySelector";

/*
  The picker offers one kind, when it is told which.

  A dashboard shows streams or saved queries and never both; the server refuses
  a panel that would mix them. So a picker that offers the other kind is
  offering a refusal, arriving after the person has already chosen -- the one
  place in the application where showing both halves is worse than partitioning
  them. (Searching by name is the opposite case and deliberately shows both:
  somebody looking for a query by its name does not know which half it is in.)
*/
// The search is debounced, so this waits in real milliseconds rather than
// flushing microtasks: a settle that only drains promises never reaches the
// call at all, and the component is left saying "Searching...".
async function settle(wrapper, times = 8) {
  for (let index = 0; index < times; index += 1) {
    // eslint-disable-next-line no-await-in-loop
    await new Promise((resolve) => setTimeout(resolve, 60));
    wrapper.update();
  }
}

const SAVED = { id: 1, name: "Revenue", is_streaming: false, is_draft: false, tags: [] };
const STREAMING = { id: 2, name: "Orders now", is_streaming: true, is_draft: false, tags: [] };

describe("QuerySelector", () => {
  beforeEach(() => {
    jest.spyOn(Query, "recent").mockResolvedValue([SAVED, STREAMING]);
    jest.spyOn(Query, "query").mockResolvedValue({ results: [SAVED, STREAMING] });
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  async function render(props = {}) {
    const wrapper = mount(<QuerySelector onChange={() => {}} {...props} />);
    await settle(wrapper);
    return wrapper;
  }

  test("a search asks the server for the half it wants", async () => {
    const wrapper = await render({ kind: "streaming" });
    wrapper
      .find("input")
      .first()
      .simulate("change", { target: { value: "orders" } });
    await settle(wrapper);

    expect(Query.query).toHaveBeenCalledWith(expect.objectContaining({ kind: "streaming" }));
  });

  // `api/queries/recent` is a short list of what this person touched and has
  // no filter of its own, so the half is applied here.
  test("and the recent list is narrowed in the browser", async () => {
    const wrapper = await render({ kind: "saved" });

    expect(wrapper.text()).toContain("Revenue");
    expect(wrapper.text()).not.toContain("Orders now");
  });

  test("the other half gets the other one", async () => {
    const wrapper = await render({ kind: "streaming" });

    expect(wrapper.text()).toContain("Orders now");
    expect(wrapper.text()).not.toContain("Revenue");
  });

  test("and a picker told nothing still offers everything", async () => {
    // Every other caller: a parameter mapping, an alert's query, a textbox.
    // None of them cares which half a query is in.
    const wrapper = await render();

    expect(wrapper.text()).toContain("Revenue");
    expect(wrapper.text()).toContain("Orders now");
  });
});
