import whenOnScreen, { revealAllCharts, isDeferringOffscreenCharts, resetOffscreenDeferralForTests } from "./offscreen";

/*
  What this has to get right is narrow and the failure is silent: a chart that
  is never told it is on screen is a blank rectangle, with nothing raised and
  nothing logged. So the three ways a caller can be woken -- scrolled to,
  revealed for a capture, or no observer at all -- are each pinned here.
*/

interface FakeObserver {
  element: Element | null;
  disconnected: boolean;
  fire: (isIntersecting: boolean) => void;
}

let observers: FakeObserver[] = [];

function installFakeObserver() {
  observers = [];
  (global as any).IntersectionObserver = class {
    private callback: (entries: any[]) => void;

    element: Element | null = null;

    disconnected = false;

    constructor(callback: (entries: any[]) => void) {
      this.callback = callback;
      observers.push(this as any);
    }

    observe(element: Element) {
      this.element = element;
    }

    disconnect() {
      this.disconnected = true;
    }

    fire(isIntersecting: boolean) {
      this.callback([{ isIntersecting }]);
    }
  } as any;
}

const node = () => ({}) as Element;

describe("deferring a chart until it is on screen", () => {
  beforeEach(() => {
    resetOffscreenDeferralForTests();
    installFakeObserver();
  });

  afterEach(() => {
    delete (global as any).IntersectionObserver;
  });

  test("nothing is drawn until the element comes into view", () => {
    const draw = jest.fn();
    whenOnScreen(node(), draw);

    expect(draw).not.toHaveBeenCalled();

    observers[0].fire(true);
    expect(draw).toHaveBeenCalledTimes(1);
  });

  test("an element that scrolls past without intersecting is left alone", () => {
    const draw = jest.fn();
    whenOnScreen(node(), draw);

    observers[0].fire(false);
    expect(draw).not.toHaveBeenCalled();
  });

  test("once woken, it stops watching", () => {
    whenOnScreen(node(), () => {});

    observers[0].fire(true);
    expect(observers[0].disconnected).toBe(true);
  });

  test("a second intersection does not draw twice", () => {
    const draw = jest.fn();
    whenOnScreen(node(), draw);

    observers[0].fire(true);
    observers[0].fire(true);
    expect(draw).toHaveBeenCalledTimes(1);
  });

  test("disposing before it is seen stops the watch and never draws", () => {
    // A widget removed from the page while below the fold. A late callback --
    // one already queued when the observer was disconnected -- must not build
    // a chart into a container that has gone.
    const draw = jest.fn();
    const stop = whenOnScreen(node(), draw);

    stop();
    expect(observers[0].disconnected).toBe(true);

    observers[0].fire(true);
    expect(draw).not.toHaveBeenCalled();
  });

  test("revealing after it has already been seen does not draw it again", () => {
    const draw = jest.fn();
    whenOnScreen(node(), draw);

    observers[0].fire(true);
    revealAllCharts();

    expect(draw).toHaveBeenCalledTimes(1);
  });

  test("revealing draws everything still waiting", () => {
    // The dashboard export and the screenshot renderer capture a document
    // taller than the window, so "in the viewport" is the wrong question.
    const first = jest.fn();
    const second = jest.fn();
    whenOnScreen(node(), first);
    whenOnScreen(node(), second);

    revealAllCharts();

    expect(first).toHaveBeenCalledTimes(1);
    expect(second).toHaveBeenCalledTimes(1);
    expect(observers.every((o) => o.disconnected)).toBe(true);
  });

  test("after revealing, later charts draw immediately and never wait", () => {
    revealAllCharts();

    const draw = jest.fn();
    whenOnScreen(node(), draw);

    expect(draw).toHaveBeenCalledTimes(1);
    expect(observers).toHaveLength(0);
    expect(isDeferringOffscreenCharts()).toBe(false);
  });

  test("a browser with no IntersectionObserver draws straight away", () => {
    delete (global as any).IntersectionObserver;

    const draw = jest.fn();
    const stop = whenOnScreen(node(), draw);

    expect(draw).toHaveBeenCalledTimes(1);
    expect(() => stop()).not.toThrow();
  });
});
