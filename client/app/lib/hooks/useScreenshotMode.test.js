import React from "react";
import ReactDOM from "react-dom";
import { act } from "react-dom/test-utils";

import useScreenshotMode, { SCREENSHOT_ATTRIBUTE, inScreenshotMode } from "./useScreenshotMode";
import location from "@/services/location";

/*
  The signal a renderer waits for.

  Without it the normal failure is a photograph of a loading spinner: the page
  is "loaded" long before it has drawn anything, and nothing else on the page
  says otherwise. Superset's docs describe checking captures for blank content
  afterwards, which is the position you are left in when the page never says.

  So the attribute must not appear early, and must appear eventually.
*/

jest.mock("@/services/location", () => ({ __esModule: true, default: { search: {} } }));

function render(ready) {
  function Probe({ isReady }) {
    useScreenshotMode(isReady);
    return null;
  }
  const container = document.createElement("div");
  const mount = (isReady) =>
    act(() => {
      ReactDOM.render(<Probe isReady={isReady} />, container);
    });
  mount(ready);
  return {
    rerender: mount,
    unmount: () => act(() => ReactDOM.unmountComponentAtNode(container)),
  };
}

const drawn = () => document.documentElement.getAttribute(SCREENSHOT_ATTRIBUTE);

/**
 * Let the fonts promise resolve and the stillness sampler run to a verdict.
 *
 * The hook samples the page every 150ms and wants two matching samples, so
 * this drives several rounds rather than one.
 */
async function settle() {
  for (let round = 0; round < 8; round++) {
    // eslint-disable-next-line no-await-in-loop
    await act(async () => {
      await Promise.resolve();
      jest.advanceTimersByTime(200);
      await Promise.resolve();
    });
  }
}

describe("useScreenshotMode", () => {
  let rendered;

  beforeEach(() => {
    jest.useFakeTimers();
    // jsdom has no rAF that fake timers drive; a timeout stands in for a frame.
    window.requestAnimationFrame = (callback) => setTimeout(callback, 0);
    location.search = {};
    document.documentElement.removeAttribute(SCREENSHOT_ATTRIBUTE);
    rendered = null;
  });

  afterEach(() => {
    if (rendered) {
      rendered.unmount();
    }
    document.documentElement.removeAttribute(SCREENSHOT_ATTRIBUTE);
    jest.useRealTimers();
  });

  describe("inScreenshotMode", () => {
    test("is off for anyone reading the page", () => {
      expect(inScreenshotMode()).toBe(false);
    });

    test("is on when asked for", () => {
      location.search = { screenshot: "1" };
      expect(inScreenshotMode()).toBe(true);
    });
  });

  test("says nothing at all when nobody is photographing", async () => {
    rendered = render(true);
    await settle();

    expect(drawn()).toBeNull();
  });

  test("does not say drawn before there is anything to draw", async () => {
    // The whole point: this is the moment a renderer would capture a spinner.
    location.search = { screenshot: "1" };
    rendered = render(false);
    await settle();

    expect(drawn()).toBeNull();
  });

  test("says drawn once the page is ready", async () => {
    location.search = { screenshot: "1" };
    rendered = render(false);
    await settle();

    rendered.rerender(true);
    await settle();

    expect(drawn()).toBe("true");
  });

  test("takes it back if the page stops being ready", async () => {
    // A dashboard that starts refreshing again is not a finished picture.
    location.search = { screenshot: "1" };
    rendered = render(true);
    await settle();
    expect(drawn()).toBe("true");

    rendered.rerender(false);

    expect(drawn()).toBeNull();
  });

  test("leaves nothing behind when it goes", async () => {
    location.search = { screenshot: "1" };
    rendered = render(true);
    await settle();
    expect(drawn()).toBe("true");

    rendered.unmount();
    rendered = null;

    expect(drawn()).toBeNull();
  });
});

/*
  The reason the sampler exists.

  The first version waited for the data and two animation frames, and produced
  a counter whose sparkline was a 90px sliver in the corner of a box 1350px
  wide: ECharts had drawn at the size its container had before the flex layout
  resolved, and viz-lib's resize watcher polls at 100ms. The data was in, the
  frames had passed, and the picture was still wrong.
*/
describe("waiting for the page to stop moving", () => {
  let rendered;
  let canvas;

  beforeEach(() => {
    jest.useFakeTimers();
    window.requestAnimationFrame = (callback) => setTimeout(callback, 0);
    location.search = { screenshot: "1" };
    document.documentElement.removeAttribute(SCREENSHOT_ATTRIBUTE);
    canvas = document.createElement("canvas");
    canvas.width = 90;
    canvas.height = 60;
    document.body.appendChild(canvas);
    rendered = null;
  });

  afterEach(() => {
    if (rendered) {
      rendered.unmount();
    }
    canvas.remove();
    document.documentElement.removeAttribute(SCREENSHOT_ATTRIBUTE);
    jest.useRealTimers();
  });

  test("does not say drawn while a chart is still growing", async () => {
    rendered = render(true);

    // Every sample sees a different canvas, the way a chart mid-resize does.
    for (let round = 0; round < 4; round++) {
      canvas.width += 100;
      // eslint-disable-next-line no-await-in-loop
      await act(async () => {
        await Promise.resolve();
        jest.advanceTimersByTime(200);
        await Promise.resolve();
      });
    }

    expect(document.documentElement.getAttribute(SCREENSHOT_ATTRIBUTE)).toBeNull();
  });

  test("says drawn once it holds still", async () => {
    rendered = render(true);
    canvas.width = 1350;

    await settle();

    expect(document.documentElement.getAttribute(SCREENSHOT_ATTRIBUTE)).toBe("true");
  });

  test("gives up and takes the picture on a page that never settles", async () => {
    // A live dashboard ticking every second must still be photographed: a
    // slightly early picture beats a timeout and no picture at all.
    rendered = render(true);

    for (let round = 0; round < 80; round++) {
      canvas.width += 1;
      // eslint-disable-next-line no-await-in-loop
      await act(async () => {
        await Promise.resolve();
        jest.advanceTimersByTime(200);
        await Promise.resolve();
      });
    }

    expect(document.documentElement.getAttribute(SCREENSHOT_ATTRIBUTE)).toBe("true");
  });
});
