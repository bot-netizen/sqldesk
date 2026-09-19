import QueryResult from "./query-result";
import { Query } from "./query";

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
    expect(query.getQueryResult().source).toBe("cached");
    expect(QueryResult.getById).toHaveBeenCalledWith(1, 21);
    expect(QueryResult.getByQueryId).not.toHaveBeenCalled();
  });

  test("any stated age is asked of the server, every time", () => {
    // Refresh (0), live (-1) and auto-refresh (N) each used to get the cached
    // result instead, so after the first load nothing ever changed.
    const query = savedQuery();
    query.getQueryResult();
    [0, -1, 300].forEach((maxAge) => {
      expect(query.getQueryResult(maxAge).source).toBe("server");
      expect(QueryResult.getByQueryId).toHaveBeenLastCalledWith(1, {}, false, maxAge);
    });
    expect(QueryResult.getByQueryId).toHaveBeenCalledTimes(3);
  });
});
