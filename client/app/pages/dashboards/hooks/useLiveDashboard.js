import { useCallback, useEffect, useRef, useState } from "react";
import { get, isFunction } from "lodash";
import { Dashboard } from "@/services/dashboard";

/*
  A viewer of a live dashboard. The server runs the queries; this only has to
  say it is watching, notice when a widget has a newer result than the one on
  screen, and fetch that result -- never run a query itself.

  "Watching" means the tab is visible. A hidden tab says it is leaving and
  stops checking in, and the server stops refreshing a dashboard nobody is
  watching, so a dashboard left open in a background tab costs nothing.
*/

const DEFAULT_CHECK_IN_SECONDS = 15;

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

export default function useLiveDashboard({ dashboard, loadWidget, publicToken = null }) {
  const [live, setLive] = useState(dashboard.live || null);
  const [lastUpdate, setLastUpdate] = useState(null);
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
    let unmounted = false;

    const checkIn = () =>
      send({ viewer: viewer.current })
        .then((response) => {
          if (unmounted) {
            return;
          }
          // Paused, resumed or switched off by somebody else.
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
        // A missed check-in is simply retried on the next tick.
        .catch(() => {});

    const start = () => {
      if (timer === null) {
        checkIn();
        timer = setInterval(checkIn, checkInMs);
      }
    };
    const stop = () => {
      if (timer !== null) {
        clearInterval(timer);
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
