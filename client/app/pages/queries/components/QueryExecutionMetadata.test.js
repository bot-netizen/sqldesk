import React from "react";
import { mount } from "enzyme";

import QueryExecutionMetadata from "./QueryExecutionMetadata";

/*
  The corner under the results, while a query is running.

  A stream query re-runs every couple of seconds for as long as somebody
  watches, so it is "executing" nearly all the time. This corner used to report
  that the way it reports a warehouse query: "Query in queue", a Cancel button
  and a timer counting up from Start streaming -- found in the picture of a
  streaming chart taken for the website, beside a chart that was filling up.
*/

jest.mock("@/components/EditVisualizationButton/QueryControlDropdown", () => () => null);
jest.mock("@/components/EditVisualizationButton", () => () => null);
jest.mock("../hooks/useAddToDashboardDialog", () => () => () => {});
jest.mock("../hooks/useEmbedDialog", () => () => () => {});
jest.mock("@/lib/useQueryResultData", () => () => ({
  rows: [{ n: 1 }, { n: 2 }],
  columns: [{ name: "n" }],
  truncated: false,
  runtime: 0.004,
  metadata: {},
  retrievedAt: "2026-11-06T22:16:00Z",
}));

function render(props) {
  return mount(
    <QueryExecutionMetadata
      query={{ id: 21, api_key: "k" }}
      queryResult={{}}
      isQueryExecuting
      executionStatus="waiting"
      executionStartedAt={Date.now() - 38000}
      {...props}
    />
  );
}

describe("QueryExecutionMetadata", () => {
  test("a warehouse query in the queue says so and can be cancelled", () => {
    const wrapper = render();
    expect(wrapper.text()).toContain("Query in queue");
    expect(wrapper.text()).toContain("Running");
    expect(wrapper.find("button").filterWhere((b) => b.text() === "Cancel")).toHaveLength(1);
  });

  test("a stream query being refreshed does not claim to be queued", () => {
    const wrapper = render({ isStream: true });
    expect(wrapper.text()).not.toContain("Query in queue");
    expect(wrapper.text()).not.toContain("Running");
    expect(wrapper.find("button").filterWhere((b) => b.text() === "Cancel")).toHaveLength(0);
  });

  test("it reads as a result that keeps being replaced", () => {
    const wrapper = render({ isStream: true });
    expect(wrapper.text()).toContain("2 rows");
    expect(wrapper.text()).toContain("Refreshed");
    // A window is read in milliseconds; a runtime would only say "0 seconds".
    expect(wrapper.text()).not.toContain("runtime");
  });

  test("a finished warehouse query still reports its runtime", () => {
    const wrapper = render({ isQueryExecuting: false, executionStatus: "done" });
    expect(wrapper.text()).toContain("runtime");
    expect(wrapper.text()).toContain("Refreshed");
  });
});
