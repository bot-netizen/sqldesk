import React from "react";
import ReactDOM from "react-dom";
import { act } from "react-dom/test-utils";

import useDashboardCycle from "./useDashboardCycle";

/*
  A wall display is left running for weeks, so the two things that matter here
  are both about the long run: it has to keep its place in the rotation, and it
  has to keep time from the clock rather than by counting ticks -- a tab that
  is throttled or briefly asleep would otherwise fall further behind every
  hour and eventually be showing the wrong dashboard for minutes at a time.
*/

function render(tokens, dwell) {
  const seen = { current: null, progress: null };
  function Probe() {
    const state = useDashboardCycle(tokens, dwell);
    seen.current = state.current;
    seen.progress = state.progress;
    return null;
  }
  const container = document.createElement("div");
  act(() => {
    ReactDOM.render(<Probe />, container);
  });
  return {
    seen,
    unmount: () => act(() => ReactDOM.unmountComponentAtNode(container)),
  };
}

/** Move both the fake clock and Date.now, which the hook reads. */
function advance(ms) {
  act(() => {
    jest.advanceTimersByTime(ms);
  });
}

let intervals;

beforeEach(() => {
  jest.useFakeTimers();
  jest.setSystemTime(new Date("2026-01-01T00:00:00Z"));
  // Counted rather than read off jest's timer count, which also sees React's
  // own scheduling and would make these tests about the wrong thing.
  intervals = { started: 0, stopped: 0 };
  // The fake timers are already in place, so these are the fake versions --
  // calling through to them keeps advanceTimersByTime working.
  const fakeSetInterval = global.setInterval;
  const fakeClearInterval = global.clearInterval;
  jest.spyOn(global, "setInterval").mockImplementation((fn, ms) => {
    intervals.started += 1;
    return fakeSetInterval(fn, ms);
  });
  jest.spyOn(global, "clearInterval").mockImplementation((id) => {
    intervals.stopped += 1;
    return fakeClearInterval(id);
  });
});

afterEach(() => {
  jest.restoreAllMocks();
  jest.useRealTimers();
});

describe("cycling a wall through dashboards", () => {
  test("one dashboard never moves, and starts no timer", () => {
    const view = render(["only"], 60);

    expect(view.seen.current).toBe(0);
    expect(view.seen.progress).toBe(0);
    // Nothing scheduled: a wall showing one dashboard should be idle between
    // its refreshes, not waking four times a second forever.
    expect(intervals.started).toBe(0);

    view.unmount();
  });

  test("moves to the next when its turn is up", () => {
    const view = render(["a", "b", "c"], 60);

    expect(view.seen.current).toBe(0);
    advance(60_000);
    expect(view.seen.current).toBe(1);
    advance(60_000);
    expect(view.seen.current).toBe(2);

    view.unmount();
  });

  test("comes back round to the first", () => {
    const view = render(["a", "b"], 30);

    advance(30_000);
    expect(view.seen.current).toBe(1);
    advance(30_000);
    expect(view.seen.current).toBe(0);

    view.unmount();
  });

  test("reports how far through the turn it is", () => {
    const view = render(["a", "b"], 60);

    advance(30_000);
    expect(view.seen.progress).toBeGreaterThan(0.4);
    expect(view.seen.progress).toBeLessThan(0.6);

    view.unmount();
  });

  test("progress starts again at each change", () => {
    const view = render(["a", "b"], 60);

    advance(60_000);
    expect(view.seen.current).toBe(1);
    expect(view.seen.progress).toBe(0);

    view.unmount();
  });

  test("a tab that was asleep catches up instead of falling behind", () => {
    // Counting ticks, an hour asleep would leave it an hour behind. Reading
    // the clock, the turn is simply over.
    const view = render(["a", "b", "c"], 60);

    // One tick fires, but an hour of wall time has passed.
    jest.setSystemTime(new Date("2026-01-01T01:00:00Z"));
    advance(250);

    expect(view.seen.current).toBe(1);

    view.unmount();
  });

  test("stops when the wall is taken down", () => {
    const view = render(["a", "b"], 60);
    expect(intervals.started).toBe(1);
    expect(intervals.stopped).toBe(0);

    view.unmount();

    expect(intervals.stopped).toBe(1);
  });
});
