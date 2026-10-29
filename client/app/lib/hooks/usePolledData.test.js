import React from "react";
import { mount } from "enzyme";
import { act } from "react-dom/test-utils";

import usePolledData from "./usePolledData";

/*
  The behaviour this hook exists for: a refresh that fails must not take the
  page with it. The cases that matter are the three failures -- the first load,
  a lost session, and everything else -- plus not piling requests up on a tab
  nobody is looking at.
*/

let hook;

function Harness({ load, options }) {
  hook = usePolledData(load, options);
  return null;
}

function render(load, options = {}) {
  let wrapper;
  act(() => {
    wrapper = mount(<Harness load={load} options={{ intervalMs: 1000, ...options }} />);
  });
  return wrapper;
}

/** Lets the promises in flight settle. */
async function settle() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

function httpError(status) {
  return Object.assign(new Error(`Request failed with status code ${status}`), {
    isAxiosError: true,
    response: { status },
  });
}

describe("usePolledData", () => {
  let logged;

  beforeEach(() => {
    jest.useFakeTimers();
    logged = jest.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    jest.useRealTimers();
    logged.mockRestore();
  });

  test("loads once on mount and again on each tick", async () => {
    const load = jest.fn(() => Promise.resolve("figures"));
    render(load);
    await settle();

    expect(hook.data).toBe("figures");

    await act(async () => {
      jest.advanceTimersByTime(1000);
      await Promise.resolve();
    });

    expect(load).toHaveBeenCalledTimes(2);
  });

  test("a failed refresh keeps the figures, marks them stale, and does not escalate", async () => {
    const onError = jest.fn();
    const load = jest.fn().mockResolvedValueOnce("figures").mockRejectedValueOnce(httpError(502));
    render(load, { onError });
    await settle();

    await act(async () => {
      jest.advanceTimersByTime(1000);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(hook.data).toBe("figures");
    expect(hook.failedAt).not.toBeNull();
    // Kept from the load that worked, so the page can say how old the
    // figures on it are rather than implying they are current.
    expect(hook.loadedAt).not.toBeNull();
    expect(hook.loadedAt).toBeLessThanOrEqual(hook.failedAt);
    expect(onError).not.toHaveBeenCalled();
    expect(logged).toHaveBeenCalled();
  });

  test("and the next refresh that works clears the mark", async () => {
    const load = jest.fn().mockResolvedValueOnce("old").mockRejectedValueOnce(httpError(502)).mockResolvedValue("new");
    render(load);
    await settle();
    await act(async () => {
      jest.advanceTimersByTime(1000);
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(hook.failedAt).not.toBeNull();

    await act(async () => {
      jest.advanceTimersByTime(1000);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(hook.data).toBe("new");
    expect(hook.failedAt).toBeNull();
  });

  test("the first load failing is escalated: there is nothing to show", async () => {
    const onError = jest.fn();
    const error = httpError(500);
    render(jest.fn(() => Promise.reject(error)), { onError });
    await settle();

    expect(onError).toHaveBeenCalledWith(error);
    expect(hook.data).toBeNull();
  });

  test.each([401, 403])("a %i is escalated even with figures in hand: polling cannot fix it", async (status) => {
    const onError = jest.fn();
    const error = httpError(status);
    const load = jest.fn().mockResolvedValueOnce("figures").mockRejectedValue(error);
    render(load, { onError });
    await settle();

    await act(async () => {
      jest.advanceTimersByTime(1000);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(onError).toHaveBeenCalledWith(error);
  });

  test("a hidden tab is left alone", async () => {
    const load = jest.fn(() => Promise.resolve("figures"));
    render(load);
    await settle();
    const hidden = jest.spyOn(document, "hidden", "get").mockReturnValue(true);

    await act(async () => {
      jest.advanceTimersByTime(3000);
      await Promise.resolve();
    });

    expect(load).toHaveBeenCalledTimes(1);
    hidden.mockRestore();
  });

  test("a tick while a request is still in flight is skipped", async () => {
    let release;
    const load = jest.fn(() => new Promise((resolve) => (release = resolve)));
    render(load);

    await act(async () => {
      jest.advanceTimersByTime(3000);
      await Promise.resolve();
    });
    expect(load).toHaveBeenCalledTimes(1);

    await act(async () => {
      release("figures");
      await Promise.resolve();
    });
    expect(hook.data).toBe("figures");
  });

  test("nothing is set after the page has gone", async () => {
    let release;
    const onError = jest.fn();
    const shown = render(
      jest.fn(() => new Promise((resolve, reject) => (release = reject))),
      { onError }
    );

    shown.unmount();
    await act(async () => {
      release(httpError(500));
      await Promise.resolve();
    });

    expect(onError).not.toHaveBeenCalled();
  });

  test("disabled means no requests at all", async () => {
    const load = jest.fn(() => Promise.resolve("figures"));
    render(load, { enabled: false });
    await settle();

    await act(async () => {
      jest.advanceTimersByTime(5000);
      await Promise.resolve();
    });

    expect(load).not.toHaveBeenCalled();
  });
});
