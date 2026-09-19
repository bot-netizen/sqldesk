import React from "react";
import { mount } from "enzyme";
import { act } from "react-dom/test-utils";
import { Dashboard } from "@/services/dashboard";
import useLiveDashboard from "./useLiveDashboard";

jest.mock("@/services/dashboard", () => ({
  Dashboard: { watchLive: jest.fn(), watchPublicLive: jest.fn() },
}));

function widget(id, resultId) {
  return {
    id,
    loading: false,
    getQueryResult: () => (resultId === null ? null : { getId: () => resultId }),
  };
}

function Harness({ dashboard, loadWidget, publicToken, onState }) {
  const state = useLiveDashboard({ dashboard, loadWidget, publicToken });
  onState(state);
  return null;
}

function setVisibility(value) {
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => value });
  document.dispatchEvent(new Event("visibilitychange"));
}

async function flush() {
  // Let the check-in promise and its .then run.
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

// Every harness mounted by a test, unmounted after it: a mounted one keeps its
// visibility listener, and would answer the next test's visibility changes.
let mounted = [];
function mountHarness(element) {
  const wrapper = mount(element);
  mounted.push(wrapper);
  return wrapper;
}

describe("useLiveDashboard", () => {
  const live = { interval: 30, paused: false, check_in_seconds: 15 };

  beforeEach(() => {
    jest.useFakeTimers();
    Dashboard.watchLive.mockReset();
    Dashboard.watchPublicLive.mockReset();
    setVisibility("visible");
  });

  afterEach(() => {
    mounted.forEach((w) => {
      if (w.exists()) {
        w.unmount();
      }
    });
    mounted = [];
    jest.useRealTimers();
  });

  test("does nothing for a dashboard that is not live", async () => {
    mountHarness(<Harness dashboard={{ id: 1, widgets: [], live: null }} loadWidget={jest.fn()} onState={() => {}} />);
    await flush();
    expect(Dashboard.watchLive).not.toHaveBeenCalled();
  });

  test("checks in straight away, and reloads only the widgets with a newer result", async () => {
    Dashboard.watchLive.mockResolvedValue({ live, results: { 10: 500, 11: 601, 12: null } });
    const loadWidget = jest.fn();
    const dashboard = { id: 1, live, widgets: [widget(10, 500), widget(11, 600), widget(12, null)] };

    mountHarness(<Harness dashboard={dashboard} loadWidget={loadWidget} onState={() => {}} />);
    await flush();

    expect(Dashboard.watchLive).toHaveBeenCalledWith({ id: 1 }, { viewer: expect.any(String) });
    // 10 is current, 12 has no result yet; only 11 changed.
    expect(loadWidget).toHaveBeenCalledTimes(1);
    // Forced, but any stored result will do: a viewer never runs the query.
    expect(loadWidget).toHaveBeenCalledWith(dashboard.widgets[1], true, -1);
  });

  test("checks in again every interval with the same viewer id", async () => {
    Dashboard.watchLive.mockResolvedValue({ live, results: {} });
    mountHarness(<Harness dashboard={{ id: 1, live, widgets: [] }} loadWidget={jest.fn()} onState={() => {}} />);
    await flush();
    act(() => {
      jest.advanceTimersByTime(15000);
    });
    await flush();
    expect(Dashboard.watchLive).toHaveBeenCalledTimes(2);
    const [first, second] = Dashboard.watchLive.mock.calls.map((c) => c[1].viewer);
    expect(second).toBe(first);
  });

  test("a hidden tab says it is leaving and stops; showing it again starts again", async () => {
    Dashboard.watchLive.mockResolvedValue({ live, results: {} });
    mountHarness(<Harness dashboard={{ id: 1, live, widgets: [] }} loadWidget={jest.fn()} onState={() => {}} />);
    await flush();

    act(() => setVisibility("hidden"));
    expect(Dashboard.watchLive).toHaveBeenLastCalledWith({ id: 1 }, { viewer: expect.any(String), leaving: true });
    const callsWhenHidden = Dashboard.watchLive.mock.calls.length;
    act(() => {
      jest.advanceTimersByTime(60000);
    });
    expect(Dashboard.watchLive).toHaveBeenCalledTimes(callsWhenHidden);

    act(() => setVisibility("visible"));
    await flush();
    expect(Dashboard.watchLive).toHaveBeenCalledTimes(callsWhenHidden + 1);
    expect(Dashboard.watchLive.mock.calls[callsWhenHidden][1].leaving).toBeUndefined();
  });

  test("leaving the page says so", async () => {
    Dashboard.watchLive.mockResolvedValue({ live, results: {} });
    const wrapper = mountHarness(
      <Harness dashboard={{ id: 1, live, widgets: [] }} loadWidget={jest.fn()} onState={() => {}} />
    );
    await flush();
    wrapper.unmount();
    expect(Dashboard.watchLive).toHaveBeenLastCalledWith({ id: 1 }, { viewer: expect.any(String), leaving: true });
  });

  test("hears when somebody else pauses it", async () => {
    Dashboard.watchLive.mockResolvedValue({ live: { ...live, paused: true }, results: {} });
    let state;
    mountHarness(
      <Harness dashboard={{ id: 1, live, widgets: [] }} loadWidget={jest.fn()} onState={(s) => (state = s)} />
    );
    await flush();
    expect(state.live.paused).toBe(true);
  });

  test("a public viewer checks in through the public link", async () => {
    Dashboard.watchPublicLive.mockResolvedValue({ live, results: {} });
    mountHarness(
      <Harness dashboard={{ live, widgets: [] }} loadWidget={jest.fn()} publicToken="abc" onState={() => {}} />
    );
    await flush();
    expect(Dashboard.watchPublicLive).toHaveBeenCalledWith({ token: "abc" }, { viewer: expect.any(String) });
    expect(Dashboard.watchLive).not.toHaveBeenCalled();
  });
});
