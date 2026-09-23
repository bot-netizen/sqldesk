import { newestStored, noOlderThan, onAutoRefresh, onPageLoad, runNow, thisResult } from "./freshness";

/*
  The bugs this file exists to prevent are all the same shape: one intent's
  value read as another's. So what is pinned is the difference between them,
  not the numbers on their own.
*/

const ALL = [
  ["page load", onPageLoad()],
  ["refresh", runNow()],
  ["newest stored", newestStored()],
  ["no older than", noOlderThan(120)],
  ["this result", thisResult(4321)],
];

describe("how fresh a result has to be", () => {
  test("only a page load settles for the result already in hand", () => {
    // Refresh, live and auto-refresh each used to get the cached result
    // instead, so after the first load nothing ever changed again.
    expect(onPageLoad().reuseLoaded).toBe(true);
    ALL.filter(([name]) => name !== "page load").forEach(([, request]) => {
      expect(request.reuseLoaded).toBe(false);
    });
  });

  test("refresh runs the query", () => {
    expect(runNow().maxAge).toBe(0);
  });

  test("the newest stored result runs nothing", () => {
    expect(newestStored().maxAge).toBe(-1);
  });

  test("an age is carried through as it was given", () => {
    expect(noOlderThan(120).maxAge).toBe(120);
  });

  test("a named result carries no age at all", () => {
    // The third thing `undefined` used to mean. It is a separate field now,
    // so nothing downstream has to guess which of the three was intended.
    const request = thisResult(4321);
    expect(request.resultId).toBe(4321);
    expect(request.maxAge).toBeUndefined();
  });

  test("only a named result has one", () => {
    ALL.filter(([name]) => name !== "this result").forEach(([, request]) => {
      expect(request.resultId).toBeNull();
    });
  });

  test("page load and a named result are told apart, despite both naming no age", () => {
    // They differ only in the fields a reader looks at -- which is the point.
    expect(onPageLoad().maxAge).toBeUndefined();
    expect(thisResult(7).maxAge).toBeUndefined();
    expect(onPageLoad().reuseLoaded).not.toBe(thisResult(7).reuseLoaded);
  });

  test("every intent says which one it is", () => {
    const names = ALL.map(([, request]) => request.name);
    expect(new Set(names).size).toBe(names.length);
  });

  describe("auto-refresh", () => {
    test("does not accept the result it made itself last time", () => {
      // Ten-minute refresh: last tick's result is a little under 600 seconds
      // old when this tick fires, and must not count as fresh.
      expect(onAutoRefresh(600).maxAge).toBeLessThan(590);
      expect(onAutoRefresh(600).maxAge).toBeGreaterThan(0);
    });

    test("but does accept one another tab made", () => {
      expect(onAutoRefresh(600).reuseLoaded).toBe(false);
      expect(onAutoRefresh(600).maxAge).toBeGreaterThan(0);
    });
  });
});
