import shareInFlight, { inFlightCount, resetInFlight } from "./inFlightResults";

/*
  Two visualizations of one query used to fetch, download and parse the same
  result twice over -- about a second of blocked main thread each, on a large
  result, for identical data.

  What matters here is the pair of properties that makes sharing safe: the
  same request in flight is answered once, and a request that has finished is
  never handed out again. The second is what keeps this from quietly becoming
  a cache and showing a dashboard stale data.
*/

/** A stand-in for QueryResult: all the registry touches is toPromise(). */
function fakeResult() {
  let settle;
  const promise = new Promise((resolve, reject) => {
    settle = { resolve, reject };
  });
  return {
    toPromise: () => promise,
    resolve: (value) => settle.resolve(value),
    reject: (error) => settle.reject(error),
  };
}

/** Let the registry's own `.then` run. */
const settled = () => new Promise((resolve) => setTimeout(resolve, 0));

beforeEach(() => resetInFlight());

describe("sharing a request in flight", () => {
  test("the same request, asked for twice, is sent once", () => {
    const start = jest.fn(() => fakeResult());

    const first = shareInFlight("a", start);
    const second = shareInFlight("a", start);

    expect(start).toHaveBeenCalledTimes(1);
    expect(second).toBe(first);
  });

  test("different requests are not shared", () => {
    const start = jest.fn(() => fakeResult());

    const first = shareInFlight("a", start);
    const second = shareInFlight("b", start);

    expect(start).toHaveBeenCalledTimes(2);
    expect(second).not.toBe(first);
  });

  test("a widget that cannot say what it wants shares nothing", () => {
    // A textbox has no query at all; it must not be handed somebody's result.
    const start = jest.fn(() => fakeResult());

    shareInFlight(null, start);
    shareInFlight(null, start);
    shareInFlight(undefined, start);

    expect(start).toHaveBeenCalledTimes(3);
    expect(inFlightCount()).toBe(0);
  });

  test("once it has finished, the next ask starts a new one", async () => {
    // This shares work, it does not cache. A dashboard refreshed a minute
    // later must actually refresh.
    const results = [fakeResult(), fakeResult()];
    const start = jest.fn(() => results.shift());

    const first = shareInFlight("a", start);
    first.resolve({ rows: [] });
    await settled();

    const second = shareInFlight("a", start);

    expect(start).toHaveBeenCalledTimes(2);
    expect(second).not.toBe(first);
  });

  test("a failed request is not handed to the next asker", async () => {
    // Otherwise one bad refresh would stick to every widget that asked after.
    const results = [fakeResult(), fakeResult()];
    const start = jest.fn(() => results.shift());

    const first = shareInFlight("a", start);
    first.reject(new Error("no"));
    await settled();

    const second = shareInFlight("a", start);

    expect(start).toHaveBeenCalledTimes(2);
    expect(second).not.toBe(first);
  });

  test("nothing is left behind once everything has settled", async () => {
    const start = () => fakeResult();
    const a = shareInFlight("a", start);
    const b = shareInFlight("b", start);
    expect(inFlightCount()).toBe(2);

    a.resolve({});
    b.reject(new Error("no"));
    await settled();

    expect(inFlightCount()).toBe(0);
  });

  test("a whole dashboard of widgets on one query costs one request", () => {
    const start = jest.fn(() => fakeResult());

    // What a dashboard load does: one synchronous pass over the widgets.
    const shared = [1, 2, 3, 4, 5].map(() => shareInFlight("one-query", start));

    expect(start).toHaveBeenCalledTimes(1);
    shared.forEach((result) => expect(result).toBe(shared[0]));
  });
});
