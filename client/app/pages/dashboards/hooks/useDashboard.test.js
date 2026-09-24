import React from "react";
import { mount } from "enzyme";
import { act } from "react-dom/test-utils";
import { newestStored, noOlderThan, onPageLoad, runNow } from "@/services/freshness";
import useDashboard from "./useDashboard";

/*
  341 lines, 27 hooks, a 36-key return and the hub of all four refresh paths,
  with no test file at all.

  What is pinned here is the thing those four paths exist to get right: which
  freshness each one asks a widget for. Every bug this hook has had has been
  one path quietly using another's -- a Refresh that reused a cached result,
  an auto-refresh that accepted the result it had made itself. Everything else
  in the return is a dialog or a piece of state with its own home.
*/

jest.mock("@/services/dashboard", () => ({
  Dashboard: { save: jest.fn(), delete: jest.fn(), setLive: jest.fn() },
  collectDashboardFilters: () => [],
}));
jest.mock("@/services/auth", () => ({
  currentUser: { id: 1, isAdmin: false, hasPermission: () => false },
}));
jest.mock("@/services/policy", () => ({
  policy: { canEdit: () => true, getDashboardRefreshIntervals: () => [600, 1800, 3600] },
}));
jest.mock("@/services/recordEvent", () => jest.fn());
jest.mock("@/services/notification", () => ({ error: jest.fn(), warn: jest.fn() }));
jest.mock("@/components/dashboards/AddWidgetDialog", () => ({}));
jest.mock("@/components/dashboards/TextboxDialog", () => ({}));
jest.mock("@/components/PermissionsEditorDialog", () => ({}));
jest.mock("../components/ShareDashboardDialog", () => ({}));
jest.mock("@/components/ParameterMappingInput", () => ({
  editableMappingsToParameterMappings: (m) => m,
  synchronizeWidgetTitles: () => [],
}));
// Live is its own hook with its own tests, and it starts a timer.
jest.mock("./useLiveDashboard", () => () => ({ live: null, setLive: () => {}, lastUpdate: null }));
jest.mock("./useDuplicateDashboard", () => () => [false, () => {}]);
jest.mock("@/lib/hooks/useFullscreenHandler", () => () => [false, () => {}]);
jest.mock("./useEditModeHandler", () => ({
  __esModule: true,
  default: () => ({ editingLayout: false }),
  DashboardStatusEnum: {},
}));

function fakeWidget(id, mapTo = null) {
  return {
    id,
    load: jest.fn(() => Promise.resolve()),
    getParametersDefs: () => [],
    getQueryResult: () => null,
    getQuery: () => ({ is_safe: true }),
    getParameterMappings: () => (mapTo ? { p: { type: "dashboard-level", mapTo } } : {}),
  };
}

function fakeDashboard(widgets) {
  return {
    id: 1,
    name: "A dashboard",
    version: 1,
    is_archived: false,
    user: { id: 1 },
    widgets,
    live: null,
    dashboard_filters_enabled: false,
    getParametersDefs: () => [],
  };
}

let hook;

function Harness({ dashboard }) {
  hook = useDashboard(dashboard);
  return null;
}

function render(widgets) {
  const dashboard = fakeDashboard(widgets);
  let wrapper;
  act(() => {
    wrapper = mount(<Harness dashboard={dashboard} />);
  });
  return wrapper;
}

/** Every freshness a widget was asked for, in order. */
function asked(widget) {
  return widget.load.mock.calls.map(([request]) => request);
}

describe("useDashboard", () => {
  describe("what each path asks a widget for", () => {
    test("opening the page settles for a result already in hand", () => {
      const widget = fakeWidget(1);
      render([widget]);

      // Twice: the mount effect and the filter-toggle effect both fire on the
      // first render. Harmless precisely because this is the one intent that
      // fetches nothing when the widget already has a result -- which is what
      // `widgetLoad.test.js` pins.
      expect(asked(widget)).toHaveLength(2);
      asked(widget).forEach((request) => expect(request).toEqual(onPageLoad()));
    });

    test("a widget's own Refresh button runs the query", () => {
      const widget = fakeWidget(1);
      render([widget]);

      act(() => {
        hook.refreshWidget(widget);
      });

      expect(asked(widget).pop()).toEqual(runNow());
    });

    test("the dashboard's Refresh button runs every query", () => {
      const first = fakeWidget(1);
      const second = fakeWidget(2);
      render([first, second]);

      act(() => {
        hook.refreshDashboard();
      });

      expect(asked(first).pop()).toEqual(runNow());
      expect(asked(second).pop()).toEqual(runNow());
    });

    test("loading a single widget with nothing said is a page load", () => {
      const widget = fakeWidget(1);
      render([widget]);
      widget.load.mockClear();

      act(() => {
        hook.loadWidget(widget);
      });

      expect(asked(widget)).toEqual([onPageLoad()]);
    });
  });

  describe("auto-refresh", () => {
    beforeEach(() => jest.useFakeTimers());
    afterEach(() => jest.useRealTimers());

    test("a timer tick asks for the max age it computed, not a whole interval", () => {
      // The gap the plan named: nothing asserted that the timer actually
      // issued the age `onAutoRefresh` works out. A tab's own last result is
      // just under one interval old when the next tick fires, so accepting a
      // whole interval refreshed the dashboard every other tick at best.
      const widget = fakeWidget(1);
      render([widget]);

      act(() => {
        hook.setRefreshRate(1800);
      });
      widget.load.mockClear();

      act(() => {
        jest.advanceTimersByTime(1800 * 1000);
      });

      expect(asked(widget)).toEqual([noOlderThan(900)]);
    });

    test("and it is not the same request as pressing Refresh", () => {
      const widget = fakeWidget(1);
      render([widget]);

      act(() => {
        hook.setRefreshRate(1800);
      });
      widget.load.mockClear();

      act(() => {
        jest.advanceTimersByTime(1800 * 1000);
      });

      expect(asked(widget).pop()).not.toEqual(runNow());
      expect(asked(widget).pop()).not.toEqual(newestStored());
    });
  });

  describe("which widgets a refresh touches", () => {
    test("new values for a dashboard parameter reach only the widgets mapped to it", () => {
      const mapped = fakeWidget(1, "region");
      const unmapped = fakeWidget(2);
      render([mapped, unmapped]);
      mapped.load.mockClear();
      unmapped.load.mockClear();

      act(() => {
        hook.refreshDashboard([{ name: "region" }]);
      });

      expect(asked(mapped)).toEqual([runNow()]);
      expect(asked(unmapped)).toEqual([]);
    });

    test("with no parameters named, every widget is refreshed", () => {
      const mapped = fakeWidget(1, "region");
      const unmapped = fakeWidget(2);
      render([mapped, unmapped]);
      mapped.load.mockClear();
      unmapped.load.mockClear();

      act(() => {
        hook.refreshDashboard();
      });

      expect(asked(mapped)).toHaveLength(1);
      expect(asked(unmapped)).toHaveLength(1);
    });
  });

  test("a second Refresh while one is still running is ignored", () => {
    // Otherwise holding the button down queues a run per press.
    let finish;
    const widget = fakeWidget(1);
    widget.load.mockImplementation(() => new Promise((resolve) => (finish = resolve)));
    render([widget]);
    widget.load.mockClear();

    act(() => {
      hook.refreshDashboard();
    });
    act(() => {
      hook.refreshDashboard();
    });

    expect(asked(widget)).toHaveLength(1);
    act(() => finish());
  });
});
