import React from "react";
import ReactDOM from "react-dom";
import { act } from "react-dom/test-utils";

import useWallScroll, { scrollFraction } from "./useWallScroll";

/*
  A wall display has nobody standing at it, so a dashboard taller than the
  screen does not merely need scrolling -- without it, everything below the
  fold is never seen. Measured on the dashboard of every visualization at
  1440x900: 15 of its 25 widgets were below the fold.
*/

describe("the shape of one pass", () => {
  test("rests at the top, so the first screen can be read", () => {
    expect(scrollFraction(0)).toBe(0);
    expect(scrollFraction(0.15)).toBe(0);
  });

  test("rests at the bottom, so the last screen can be read", () => {
    expect(scrollFraction(0.7)).toBe(1);
    expect(scrollFraction(0.85)).toBe(1);
  });

  test("travels down in between, without jumping", () => {
    expect(scrollFraction(0.425)).toBeCloseTo(0.5, 5);
    // Monotonic through the descent: any step back would read as a stutter.
    let previous = -1;
    for (let p = 0.15; p <= 0.7; p += 0.01) {
      const at = scrollFraction(p);
      expect(at).toBeGreaterThanOrEqual(previous);
      previous = at;
    }
  });

  test("comes back up, so the loop closes where it started", () => {
    expect(scrollFraction(0.925)).toBeCloseTo(0.5, 5);
    expect(scrollFraction(1)).toBeCloseTo(0, 5);
  });

  test("never leaves the page", () => {
    for (let p = 0; p <= 1; p += 0.005) {
      expect(scrollFraction(p)).toBeGreaterThanOrEqual(0);
      expect(scrollFraction(p)).toBeLessThanOrEqual(1);
    }
  });
});

function render(period, key) {
  function Probe({ periodSeconds, resetKey }) {
    useWallScroll(periodSeconds, resetKey);
    return null;
  }
  const container = document.createElement("div");
  const mount = (props) =>
    act(() => {
      ReactDOM.render(<Probe {...props} />, container);
    });
  mount({ periodSeconds: period, resetKey: key });
  return {
    rerender: (props) => mount({ periodSeconds: period, ...props }),
    unmount: () => act(() => ReactDOM.unmountComponentAtNode(container)),
  };
}

function tick(ms) {
  act(() => {
    jest.advanceTimersByTime(ms);
  });
}

describe("useWallScroll", () => {
  let scrolled;
  let height;

  beforeEach(() => {
    jest.useFakeTimers();
    scrolled = [];
    height = 3500;
    window.scrollTo = (x, y) => scrolled.push(y);
    Object.defineProperty(window, "innerHeight", { value: 900, configurable: true });
    Object.defineProperty(document.documentElement, "scrollHeight", { get: () => height, configurable: true });
  });

  afterEach(() => {
    jest.clearAllTimers();
    jest.useRealTimers();
  });

  test("starts at the top", () => {
    render(60, "a");
    expect(scrolled[0]).toBe(0);
  });

  test("reaches the bottom, and no further", () => {
    render(60, "a");
    tick(60000 * 0.75);
    expect(Math.max(...scrolled)).toBe(3500 - 900);
  });

  test("is back at the top by the time the dashboard changes", () => {
    render(60, "a");
    // One tick short of the period: the next dashboard arrives here.
    tick(60000 - 100);
    expect(scrolled[scrolled.length - 1]).toBeLessThan(40);
  });

  test("a dashboard that fits is left alone", () => {
    height = 800;
    render(60, "a");
    scrolled.length = 0;
    tick(60000);
    // The initial scroll-to-top stands; nothing after it.
    expect(scrolled).toEqual([]);
  });

  test("notices a dashboard that grows as its widgets arrive", () => {
    height = 800;
    render(60, "a");
    tick(60000 * 0.4);
    const before = scrolled.length;
    height = 3500;
    tick(60000 * 0.1);
    expect(scrolled.length).toBeGreaterThan(before);
  });

  test("goes back to the top when the dashboard changes", () => {
    const { rerender } = render(60, "a");
    tick(60000 * 0.5);
    scrolled.length = 0;
    rerender({ resetKey: "b" });
    expect(scrolled[0]).toBe(0);
  });

  test("does no work without a period", () => {
    const before = jest.getTimerCount();
    render(0, "a");
    expect(jest.getTimerCount()).toBe(before);
  });
});
