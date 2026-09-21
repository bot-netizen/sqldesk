import observe from "./resizeObserver";

/*
  The bug this file exists for: one element, two watchers, and the second was
  silently dropped.

  An ECharts visualization registers twice for the same node -- `useEChart` to
  resize the canvas, `useElementSize` to measure the box the option is built
  from -- and only the first was kept. The second caller was handed a disposer
  that did nothing and never heard about a resize, so the canvas stayed
  whatever size it was created at. Measured on a dashboard: a container 698px
  wide with a 0x0 canvas in it, because the chart had been created before the
  page had laid out.

  Nothing raised, nothing logged. Hence these.

  The contract being pinned is "after a size change, every watcher is told" --
  not how many times a watcher is called while the size is holding still. The
  first registration polls synchronously and later ones wait for the next
  pass, which is an implementation detail no caller should depend on.
*/

function fakeNode(width: number, height: number) {
  const node = {
    size: { width, height },
    getBoundingClientRect() {
      return { width: node.size.width, height: node.size.height };
    },
  };
  return node;
}

/** Run the poll loop far enough for a pending check to happen. */
function poll() {
  jest.advanceTimersByTime(150);
}

describe("resizeObserver", () => {
  /*
    The watcher list is module state and the poll loop only runs while it has
    something in it, so a test that leaves a watcher behind leaves the loop
    scheduled -- and `clearAllTimers` then kills it with the list still
    occupied, which stops every later test from ever polling. Each test hands
    its disposers here and they are all called before the timers go.
  */
  let disposers: Array<() => void>;

  function watch(node: any, callback: (node: any) => void) {
    const unwatch = observe(node, callback);
    disposers.push(unwatch);
    return unwatch;
  }

  beforeEach(() => {
    jest.useFakeTimers();
    disposers = [];
  });

  afterEach(() => {
    disposers.forEach((dispose) => dispose());
    jest.clearAllTimers();
    jest.useRealTimers();
  });

  test("reports a change of size", () => {
    const node = fakeNode(100, 50);
    const seen: number[] = [];
    watch(node, () => seen.push(node.size.width));

    poll();
    node.size.width = 200;
    poll();

    expect(seen).toContain(200);
  });

  test("says nothing while the size holds still", () => {
    const node = fakeNode(100, 50);
    const seen: number[] = [];
    watch(node, () => seen.push(1));

    poll();
    const settled = seen.length;
    poll();
    poll();

    expect(seen).toHaveLength(settled);
  });

  test("two watchers on one element both hear about a change", () => {
    // The whole bug: the second of these used to be dropped on the floor.
    const node = fakeNode(0, 0);
    let canvasResized = 0;
    let boxMeasured = 0;
    watch(node, () => {
      canvasResized += 1;
    });
    watch(node, () => {
      boxMeasured += 1;
    });
    poll();

    canvasResized = 0;
    boxMeasured = 0;
    node.size.width = 698;
    poll();

    expect(canvasResized).toBe(1);
    expect(boxMeasured).toBe(1);
  });

  test("a second watcher is given a disposer that actually works", () => {
    const node = fakeNode(100, 50);
    let kept = 0;
    let dropped = 0;
    watch(node, () => {
      kept += 1;
    });
    const unwatch = watch(node, () => {
      dropped += 1;
    });
    poll();

    kept = 0;
    dropped = 0;
    unwatch();
    node.size.width = 300;
    poll();

    expect(kept).toBe(1);
    expect(dropped).toBe(0);
  });

  test("disposing one watcher leaves the element watched for the other", () => {
    const node = fakeNode(100, 50);
    let kept = 0;
    const unwatch = watch(node, () => {});
    watch(node, () => {
      kept += 1;
    });
    poll();

    kept = 0;
    unwatch();
    node.size.width = 300;
    poll();
    node.size.width = 400;
    poll();

    expect(kept).toBe(2);
  });

  test("the last watcher going stops the polling, and a new one restarts it", () => {
    const node = fakeNode(100, 50);
    let seen = 0;
    const unwatch = watch(node, () => {
      seen += 1;
    });
    poll();
    unwatch();

    seen = 0;
    node.size.width = 300;
    poll();
    poll();
    expect(seen).toBe(0);

    // Without the restart nothing on the page is ever watched again.
    let resumed = 0;
    watch(node, () => {
      resumed += 1;
    });
    node.size.width = 400;
    poll();
    expect(resumed).toBeGreaterThan(0);
  });

  test("a watcher may stop watching from inside its own callback", () => {
    // A dashboard does this: removing a widget disposes its watchers while the
    // loop is part-way through them.
    const node = fakeNode(100, 50);
    let other = 0;
    // Registered first so it is this one that starts the loop: the very first
    // registration polls synchronously, which would call the self-disposing
    // callback below before its own binding existed.
    watch(node, () => {
      other += 1;
    });
    let unwatch: (() => void) | null = null;
    unwatch = watch(node, () => {
      if (unwatch) {
        unwatch();
      }
    });

    expect(() => poll()).not.toThrow();
    other = 0;
    node.size.width = 300;
    expect(() => poll()).not.toThrow();
    expect(other).toBe(1);
  });

  test("nothing to watch is not an error", () => {
    expect(() => observe(null, () => {})()).not.toThrow();
  });
});
