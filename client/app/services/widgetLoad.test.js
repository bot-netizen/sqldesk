import Widget from "./widget";
import { Query } from "./query";
import { resetInFlight } from "./inFlightResults";
import { newestStored, onPageLoad, runNow } from "./freshness";

/*
  Two rules in `Widget.load` that nothing asserted, both of which decide
  whether a dashboard shows the right data:

  - only a page load settles for a result already in hand. It used to be a
    `force` flag turned into `maxAge = force ? 0 : undefined`, which is where
    two shipped bugs came from.
  - the result a widget shows is the one from its *latest* request. A slow
    first request landing after a second one started must not overwrite what
    the second produced -- the "identity guard" in `trackResult`.
*/

jest.mock("@sqldesk/viz/lib", () => ({
  registeredVisualizations: { CHART: { name: "Chart" } },
  preloadVisualization: () => {},
}));

/** A result that settles when the test says so. */
function deferredResult(id) {
  let settle;
  const promise = new Promise((resolve) => {
    settle = () => resolve({ id });
  });
  return { result: { toPromise: () => promise }, settle };
}

function widget(results) {
  const w = new Widget({
    id: 1,
    visualization: {
      id: 2,
      type: "CHART",
      query: { id: 7, name: "a query", query: "select 1", options: { parameters: [] } },
    },
    options: { position: { col: 0, row: 0, sizeX: 4, sizeY: 4 } },
  });
  w.getQuery().getParameters = () => ({ getExecutionValues: () => ({}) });
  // Stand in for the whole request path: one result per call, in order.
  const fetched = [];
  Query.prototype.getQueryResult = jest.fn(function getQueryResult() {
    const next = results[fetched.length];
    fetched.push(next);
    return next;
  });
  return { w, fetched, calls: () => Query.prototype.getQueryResult.mock.calls };
}

beforeEach(() => resetInFlight());

describe("Widget.load", () => {
  test("a page load fetches once and then settles for what it has", async () => {
    const first = deferredResult(1);
    const { w, calls } = widget([first.result]);

    const loading = w.load(onPageLoad());
    first.settle();
    await loading;

    await w.load(onPageLoad());

    expect(calls()).toHaveLength(1);
  });

  test("every other intent fetches again, even with a result on screen", async () => {
    const first = deferredResult(1);
    const second = deferredResult(2);
    const third = deferredResult(3);
    const { w, calls } = widget([first.result, second.result, third.result]);

    const loading = w.load(onPageLoad());
    first.settle();
    await loading;

    const refreshing = w.load(runNow());
    second.settle();
    await refreshing;

    const again = w.load(newestStored());
    third.settle();
    await again;

    expect(calls()).toHaveLength(3);
  });

  test("a widget with nothing to show fetches nothing", async () => {
    const textbox = new Widget({ id: 1, text: "hello", options: {} });
    await expect(textbox.load(runNow())).resolves.toBeUndefined();
  });
});

describe("the result a widget shows", () => {
  test("is the latest one asked for, even when an earlier request lands after it", async () => {
    // A page load still in flight when somebody presses Refresh. The slow
    // first reply arriving second must not put stale rows on the screen.
    //
    // Two different intents on purpose: two identical ones in the same tick
    // are one request, by design -- see inFlightResults.
    const first = deferredResult("slow");
    const second = deferredResult("fast");
    const { w } = widget([first.result, second.result]);

    w.load(onPageLoad());
    const secondLoad = w.load(runNow());

    second.settle();
    await secondLoad;
    expect(w.data).toEqual({ id: "fast" });
    expect(w.loading).toBe(false);

    first.settle();
    await first.result.toPromise();
    // One more turn, so the stale request's own `.then` has run.
    await Promise.resolve();

    expect(w.data).toEqual({ id: "fast" });
  });

  test("a widget is loading from the moment it asks until its own reply lands", async () => {
    const only = deferredResult(1);
    const { w } = widget([only.result]);

    const loading = w.load(runNow());
    expect(w.loading).toBe(true);

    only.settle();
    await loading;
    expect(w.loading).toBe(false);
  });
});
