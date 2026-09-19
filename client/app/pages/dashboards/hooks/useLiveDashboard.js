import { useCallback, useEffect, useRef, useState } from "react";
import { get, isFunction } from "lodash";
import moment from "moment";
import { Dashboard } from "@/services/dashboard";
import { serverNow, syncServerClock } from "@/lib/serverClock";

/*
  A viewer of a live dashboard. The server runs the queries; this only has to
  say it is watching, notice when a widget has a newer result than the one on
  screen, and fetch that result -- never run a query itself.

  "Watching" means the tab is visible. A hidden tab says it is leaving and
  stops checking in, and the server stops refreshing a dashboard nobody is
  watching, so a dashboard left open in a background tab costs nothing. A
  window merely behind another one is still visible, and still watching: that
  is a wall screen.

  Coming back to the tab checks in at once; the server, finding nobody was
  watching, refreshes what is stale straight away, and the tab checks in every
  few seconds until the new results are on screen.
*/

const DEFAULT_CHECK_IN_SECONDS = 15;

// While a widget is overdue -- the tab has just come back, or the server is
// running its query now -- check in this often...
export const CATCH_UP_MS = 3000;
// ...but only this many times in a row: a query that keeps failing must not
// keep every viewer polling every three seconds.
export const CATCH_UP_LIMIT = 20;
// Check in this long after a widget falls due, to find its new result ready.
export const DUE_GRACE_MS = 3000;

function newViewerId() {
  return `${Math.random().toString(36).slice(2, 10)}${Date.now().toString(36)}`;
}

function tabIsVisible() {
  return typeof document === "undefined" || document.visibilityState !== "hidden";
}

function currentResultId(widget) {
  const result = widget.getQueryResult();
  return result && isFunction(result.getId) ? result.getId() : null;
}

function resultTime(widget) {
  const result = widget.getQueryResult();
  const at = result && isFunction(result.getUpdatedAt) ? result.getUpdatedAt() : null;
  return at ? moment(at).valueOf() : null;
}

/**
 * When to check in next: the usual interval, sooner if a widget falls due
 * before then, and every few seconds while one is overdue. Widgets already
 * loading a newer result are not waiting on the server.
 */
export function nextCheckIn({ widgets, live, checkInMs, overdueChecks, now }) {
  if (!live || live.paused) {
    return { delay: checkInMs, overdue: false };
  }
  const intervalMs = live.interval * 1000;
  let earliestDue = Infinity;
  widgets.forEach((widget) => {
    const at = widget.loading ? null : resultTime(widget);
    if (at !== null) {
      earliestDue = Math.min(earliestDue, at + intervalMs);
    }
  });
  if (earliestDue === Infinity) {
    return { delay: checkInMs, overdue: false };
  }
  const untilDue = earliestDue - now;
  if (untilDue <= 0) {
    return { delay: overdueChecks < CATCH_UP_LIMIT ? CATCH_UP_MS : checkInMs, overdue: true };
  }
  return { delay: Math.min(checkInMs, untilDue + DUE_GRACE_MS), overdue: false };
}

export default function useLiveDashboard({ dashboard, loadWidget, publicToken = null }) {
  const [live, setLive] = useState(dashboard.live || null);
  const [lastUpdate, setLastUpdate] = useState(null);
  const liveRef = useRef(live);
  liveRef.current = live;
  // One id for the life of the tab: the server counts viewers, not requests.
  const viewer = useRef(newViewerId());

  // The check-in loop outlives many renders; it reads the latest dashboard and
  // loader through refs rather than restarting whenever they change.
  const dashboardRef = useRef(dashboard);
  dashboardRef.current = dashboard;
  const loadWidgetRef = useRef(loadWidget);
  loadWidgetRef.current = loadWidget;

  // A dashboard reloaded from the server, or changed by this user, brings its
  // own live settings.
  useEffect(() => {
    setLive(dashboard.live || null);
  }, [dashboard.live]);

  const isLive = !!live;
  const checkInMs = (get(live, "check_in_seconds") || DEFAULT_CHECK_IN_SECONDS) * 1000;

  const send = useCallback(
    (body) =>
      publicToken
        ? Dashboard.watchPublicLive({ token: publicToken }, body)
        : Dashboard.watchLive({ id: dashboardRef.current.id }, body),
    [publicToken]
  );

  useEffect(() => {
    if (!isLive) {
      return undefined;
    }
    let timer = null;
    let active = false;
    let unmounted = false;
    // Each time the tab becomes visible starts a new chain of check-ins; a
    // reply from before it was hidden must not start a second one.
    let generation = 0;
    let overdueChecks = 0;

    const checkIn = (gen) => {
      timer = null;
      send({ viewer: viewer.current })
        .then((response) => {
          if (unmounted) {
            return;
          }
          if (response.server_time) {
            syncServerClock(response.server_time);
          }
          // Paused, resumed or switched off by somebody else.
          liveRef.current = response.live || null;
          setLive(response.live || null);
          const results = response.results || {};
          let reloaded = 0;
          dashboardRef.current.widgets.forEach((widget) => {
            const newest = results[String(widget.id)];
            if (newest && !widget.loading && currentResultId(widget) !== newest) {
              reloaded += 1;
              // Force a fetch, but accept any stored result: the server has
              // just said a newer one exists, and a viewer must not run the
              // query itself.
              loadWidgetRef.current(widget, true, -1);
            }
          });
          if (reloaded > 0) {
            setLastUpdate(Date.now());
          }
        })
        // A missed check-in is simply retried on the next one.
        .catch(() => {})
        .then(() => {
          if (unmounted || !active || gen !== generation || timer !== null) {
            return;
          }
          const { delay, overdue } = nextCheckIn({
            widgets: dashboardRef.current.widgets,
            live: liveRef.current,
            checkInMs,
            overdueChecks,
            now: serverNow(),
          });
          overdueChecks = overdue ? overdueChecks + 1 : 0;
          timer = setTimeout(() => checkIn(gen), delay);
        });
    };

    const start = () => {
      if (!active) {
        active = true;
        generation += 1;
        overdueChecks = 0;
        checkIn(generation);
      }
    };
    const stop = () => {
      if (active) {
        active = false;
        clearTimeout(timer);
        timer = null;
        send({ viewer: viewer.current, leaving: true }).catch(() => {});
      }
    };
    const onVisibilityChange = () => (tabIsVisible() ? start() : stop());

    if (tabIsVisible()) {
      start();
    }
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      unmounted = true;
      document.removeEventListener("visibilitychange", onVisibilityChange);
      stop();
    };
  }, [isLive, checkInMs, send]);

  return { live, setLive, lastUpdate };
}
