import React from "react";
import { mount } from "enzyme";

import ApplicationArea, { REPORT_EVERY } from "./index";
import notification from "@/services/notification";

/*
  What happens to an error nobody caught.

  It used to replace the whole application, permanently: the router that went
  with it was what listened for the next navigation, so the tab was finished
  until somebody reloaded. These pin the two halves of the cure -- the
  application stays mounted, and the person is told once rather than per
  error.
*/

jest.mock("@/services/notification", () => ({ error: jest.fn(), success: jest.fn(), warn: jest.fn() }));
jest.mock("@/services/routes", () => ({ items: [] }));
jest.mock("./Router", () => {
  const React = require("react"); // eslint-disable-line global-require
  return () => <div data-test="TheRouter" />;
});

function raise(error, message = "Uncaught Error") {
  const event = new Event("error", { cancelable: true });
  event.error = error;
  event.message = message;
  window.dispatchEvent(event);
}

describe("an uncaught error", () => {
  let logged;
  let mounted;

  // jsdom reports an error event of its own through console.error, so what is
  // pinned is that ours is logged, not how many lines reach the console.
  const loggedOurs = (needle) => logged.mock.calls.some((call) => String(call[0]).includes(needle));

  function show() {
    mounted = mount(<ApplicationArea />);
    return mounted;
  }

  beforeEach(() => {
    jest.clearAllMocks();
    logged = jest.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    if (mounted) {
      // Every instance listens on window, so one left mounted answers the
      // next test's errors too.
      mounted.unmount();
      mounted = null;
    }
    logged.mockRestore();
  });

  test("leaves the application running and says so once", () => {
    const shown = show();

    raise(new TypeError("x is not a function"));
    shown.update();

    expect(shown.find('[data-test="TheRouter"]').exists()).toBe(true);
    expect(notification.error).toHaveBeenCalledTimes(1);
    expect(loggedOurs("x is not a function")).toBe(true);
  });

  test("a second error in the same minute is logged but not announced again", () => {
    show();

    raise(new TypeError("first"));
    raise(new TypeError("second"));

    expect(notification.error).toHaveBeenCalledTimes(1);
    expect(loggedOurs("second")).toBe(true);
  });

  test("a minute later it is announced again", () => {
    const clock = jest.spyOn(Date, "now");
    clock.mockReturnValue(0);
    show();

    raise(new TypeError("first"));
    clock.mockReturnValue(REPORT_EVERY + 1);
    raise(new TypeError("later"));

    expect(notification.error).toHaveBeenCalledTimes(2);
    clock.mockRestore();
  });

  test("a chunk that failed to load is left to the loader, which retries and reloads", () => {
    show();
    const error = new Error("Loading chunk admin failed.");
    error.name = "ChunkLoadError";

    raise(error);

    expect(notification.error).not.toHaveBeenCalled();
  });

  test("the layout settling is not an error anybody is told about", () => {
    show();

    // How it really arrives: a message, and no `error` at all. Every
    // visualization that scales itself to its widget can produce one, so this
    // was announcing a fault on pages that were working.
    raise(undefined, "ResizeObserver loop completed with undelivered notifications.");

    expect(notification.error).not.toHaveBeenCalled();
  });

  test("the handler is taken off again when the application unmounts", () => {
    // Dispatching an error event with nothing listening makes jsdom report it
    // and fail the test, so what is checked is that the same handler comes
    // off again -- the listener left behind is what would answer for a page
    // that is gone.
    const added = jest.spyOn(window, "addEventListener");
    const removed = jest.spyOn(window, "removeEventListener");

    show().unmount();
    mounted = null;

    const handler = added.mock.calls.find(([type]) => type === "error")[1];
    expect(removed.mock.calls.some(([type, fn]) => type === "error" && fn === handler)).toBe(true);
    added.mockRestore();
    removed.mockRestore();
  });
});
