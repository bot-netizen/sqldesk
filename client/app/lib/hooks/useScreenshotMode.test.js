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

/** Let the fonts promise and both animation frames settle. */
async function settle() {
  await act(async () => {
    await Promise.resolve();
    jest.runAllTimers();
    await Promise.resolve();
    jest.runAllTimers();
    await Promise.resolve();
  });
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
