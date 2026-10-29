import React, { useEffect } from "react";
import { mount } from "enzyme";

import recordEvent from "@/services/recordEvent";
import notifications from "@/services/notifications";
import useQueryExecute from "./useQueryExecute";

jest.mock("@/services/recordEvent", () => jest.fn());
jest.mock("@/services/notifications", () => ({ getPermissions: jest.fn(), showNotification: jest.fn() }));

/*
  The stream editor refreshes every two seconds through the same execute as
  the Run button. Each refresh recorded an execution and asked for
  notification permission -- 1,800 event rows an hour per open tab -- so a
  refresh nobody pressed for runs quietly.
*/
function harness() {
  const query = { id: 7, name: "orders", query: "select 1", hasResult: () => false, paramsRequired: () => false };
  let execute = null;
  function Harness() {
    const { executeQuery } = useQueryExecute(query);
    useEffect(() => {
      execute = executeQuery;
    });
    return null;
  }
  mount(<Harness />);
  return (options) =>
    execute(
      undefined,
      () => ({
        getUpdatedAt: () => null,
        getStatus: () => "done",
        toPromise: () => Promise.resolve({ query_result: { query: "select 1" }, getId: () => 1 }),
      }),
      options
    );
}

describe("running a query", () => {
  beforeEach(() => {
    recordEvent.mockClear();
    notifications.getPermissions.mockClear();
  });

  test("a run somebody asked for is recorded", () => {
    harness()();

    expect(recordEvent).toHaveBeenCalledWith("execute", "query", 7);
    expect(notifications.getPermissions).toHaveBeenCalled();
  });

  test("a quiet refresh is not", () => {
    harness()({ quiet: true });

    expect(recordEvent).not.toHaveBeenCalled();
    expect(notifications.getPermissions).not.toHaveBeenCalled();
  });
});
