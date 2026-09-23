import QueryResult from "./query-result";
import { Query } from "./query";
import { newestStored, noOlderThan, onPageLoad, runNow, thisResult } from "./freshness";

jest.mock("./query-result", () => {
  const getById = jest.fn(() => ({ source: "cached" }));
  const getByQueryId = jest.fn(() => ({ source: "server" }));
  return { __esModule: true, default: { getById, getByQueryId } };
});

function savedQuery() {
  // What a dashboard hands a widget: a query that knows its latest result.
  return new Query({ id: 1, query: "select 1", latest_query_data_id: 21, options: {} });
}

describe("Query.getQueryResult", () => {
  beforeEach(() => {
    QueryResult.getById.mockClear();
    QueryResult.getByQueryId.mockClear();
  });

  test("a page loading reuses the result the query already knows about", () => {
    const query = savedQuery();
    expect(query.getQueryResult(onPageLoad()).source).toBe("cached");
    expect(QueryResult.getById).toHaveBeenCalledWith(1, 21);
    expect(QueryResult.getByQueryId).not.toHaveBeenCalled();
  });

  test("every other intent is asked of the server, every time", () => {
    // Refresh, live and auto-refresh each used to get the cached result
    // instead, so after the first load nothing ever changed.
    const query = savedQuery();
    query.getQueryResult(onPageLoad());
    [runNow(), newestStored(), noOlderThan(300)].forEach((request) => {
      expect(query.getQueryResult(request).source).toBe("server");
      expect(QueryResult.getByQueryId).toHaveBeenLastCalledWith(1, {}, false, request.maxAge);
    });
    expect(QueryResult.getByQueryId).toHaveBeenCalledTimes(3);
  });

  test("a named result names no age, and still does not take the cached one", () => {
    // `thisResult` and `onPageLoad` both leave `maxAge` undefined. Reading
    // that number alone -- which is what the old code did -- makes a live
    // dashboard show the result it loaded when the page opened, for ever.
    const query = savedQuery();

    expect(query.getQueryResult(thisResult(99)).source).toBe("server");
    expect(QueryResult.getByQueryId).toHaveBeenCalledWith(1, {}, false, undefined);
  });

  test("with no intent given at all, a query assumes a page is loading", () => {
    expect(savedQuery().getQueryResult().source).toBe("cached");
  });
});
