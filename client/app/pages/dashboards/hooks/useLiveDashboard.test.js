import React from "react";
import { mount } from "enzyme";
import { act } from "react-dom/test-utils";
import { Dashboard } from "@/services/dashboard";
import { resetServerClock, serverNow } from "@/lib/serverClock";
import useLiveDashboard, { CATCH_UP_LIMIT, CATCH_UP_MS, DUE_GRACE_MS, nextCheckIn } from "./useLiveDashboard";

jest.mock("@/services/dashboard", () => ({
  Dashboard: { watchLive: jest.fn(), watchPublicLive: jest.fn() },
}));

function widget(id, resultId, updatedAt = null) {
  return {
    id,
    loading: false,
    getQueryResult: () => (resultId === null ? null : { getId: () => resultId, getUpdatedAt: () => updatedAt }),
  };
}

function secondsAgo(seconds) {
  return new Date(Date.now() - seconds * 1000).toISOString();
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
    resetServerClock();
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
    // Exactly the result the server named, by id: a viewer never runs the query.
    expect(loadWidget).toHaveBeenCalledWith(dashboard.widgets[1], true, undefined, 601);
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

  test("a public viewer, whose key cannot read results by id, asks for the newest stored one", async () => {
    Dashboard.watchPublicLive.mockResolvedValue({ live, results: { 11: 601 } });
    const loadWidget = jest.fn();
    const dashboard = { live, widgets: [widget(11, 600)] };
    mountHarness(<Harness dashboard={dashboard} loadWidget={loadWidget} publicToken="abc" onState={() => {}} />);
    await flush();
    expect(loadWidget).toHaveBeenCalledWith(dashboard.widgets[0], true, -1);
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

  test("coming back to an old result, it checks in every few seconds until the new one is there", async () => {
    // Hidden for five minutes: the server has only just been told to refresh.
    const old = widget(10, 500, secondsAgo(300));
    Dashboard.watchLive.mockResolvedValue({ live, results: { 10: 500 } });
    mountHarness(<Harness dashboard={{ id: 1, live, widgets: [old] }} loadWidget={jest.fn()} onState={() => {}} />);
    await flush();
    expect(Dashboard.watchLive).toHaveBeenCalledTimes(1);

    act(() => {
      jest.advanceTimersByTime(CATCH_UP_MS);
    });
    await flush();
    expect(Dashboard.watchLive).toHaveBeenCalledTimes(2);
  });

  test("it checks in just after the next widget falls due", async () => {
    // Refreshed 20 seconds ago on a 30-second dashboard: due in 10.
    Dashboard.watchLive.mockResolvedValue({ live, results: { 10: 500 } });
    mountHarness(
      <Harness
        dashboard={{ id: 1, live, widgets: [widget(10, 500, secondsAgo(20))] }}
        loadWidget={jest.fn()}
        onState={() => {}}
      />
    );
    await flush();

    act(() => {
      jest.advanceTimersByTime(10000 + DUE_GRACE_MS - 500);
    });
    await flush();
    expect(Dashboard.watchLive).toHaveBeenCalledTimes(1);

    act(() => {
      jest.advanceTimersByTime(1000);
    });
    await flush();
    expect(Dashboard.watchLive).toHaveBeenCalledTimes(2);
  });

  test("it takes the server's clock from a check-in", async () => {
    const serverTime = new Date(Date.now() + 3600 * 1000).toISOString();
    Dashboard.watchLive.mockResolvedValue({ live, results: {}, server_time: serverTime });
    mountHarness(<Harness dashboard={{ id: 1, live, widgets: [] }} loadWidget={jest.fn()} onState={() => {}} />);
    await flush();
    expect(Math.abs(serverNow() - Date.now() - 3600 * 1000)).toBeLessThan(1000);
  });
});

describe("nextCheckIn", () => {
  const live = { interval: 30, paused: false };
  const now = Date.parse("2026-09-19T10:00:00Z");
  const at = (secondsBefore) => new Date(now - secondsBefore * 1000).toISOString();
  const base = { live, checkInMs: 15000, overdueChecks: 0, now };

  test("the usual interval when nothing is due before it", () => {
    expect(nextCheckIn({ ...base, widgets: [widget(1, 1, at(0))] })).toEqual({ delay: 15000, overdue: false });
  });

  test("sooner when a widget falls due first", () => {
    expect(nextCheckIn({ ...base, widgets: [widget(1, 1, at(25))] }).delay).toBe(5000 + DUE_GRACE_MS);
  });

  test("the earliest widget decides", () => {
    const widgets = [widget(1, 1, at(0)), widget(2, 2, at(24))];
    expect(nextCheckIn({ ...base, widgets }).delay).toBe(6000 + DUE_GRACE_MS);
  });

  test("every few seconds while overdue, for a while", () => {
    const widgets = [widget(1, 1, at(90))];
    expect(nextCheckIn({ ...base, widgets })).toEqual({ delay: CATCH_UP_MS, overdue: true });
    expect(nextCheckIn({ ...base, widgets, overdueChecks: CATCH_UP_LIMIT })).toEqual({ delay: 15000, overdue: true });
  });

  test("a widget already loading its new result is not waiting", () => {
    const loading = { ...widget(1, 1, at(90)), loading: true };
    expect(nextCheckIn({ ...base, widgets: [loading] }).delay).toBe(15000);
  });

  test("paused, nothing is coming", () => {
    const widgets = [widget(1, 1, at(90))];
    expect(nextCheckIn({ ...base, widgets, live: { ...live, paused: true } })).toEqual({
      delay: 15000,
      overdue: false,
    });
  });
});
