import { useCallback, useEffect, useRef, useState } from "react";

/*
  A page that refreshes itself, and what it does when one refresh fails.

  The admin pages polled by handing any failure to the nearest error boundary,
  which replaces the page with an error. That is right for the first load --
  there is nothing to show -- and wrong for every refresh after it: a 502 while
  a server restarts, or a dropped request, threw away a screenful of figures
  somebody was reading, and the page could not come back on its own because the
  thing that would have polled again had been unmounted. Those pages are open
  precisely during the incidents that cause the blip.

  So a refresh that fails keeps the last answer and says it is stale, and the
  next tick quietly puts it right. Two exceptions, where polling on is
  pointless: nothing has loaded yet, and the session or the permission has gone
  (401/403) -- both go to the error boundary, which says something useful about
  each.

  While a request is in flight the timer skips its turn, and a hidden tab is
  left alone: a laptop lid closed on an admin page should not come back to an
  hour of queued requests.
*/

/** 401/403 mean something a refresh cannot fix. */
function isFatal(error) {
  const status = error && error.response ? error.response.status : error && error.status;
  return status === 401 || status === 403;
}

/**
 * Polls `load` and keeps the last answer when a refresh fails.
 *
 * @param {() => Promise<any>} load one request; its resolved value is the data
 * @param {object} options
 * @param {number} options.intervalMs how often to refresh
 * @param {(error: any) => void} options.onError handed the errors worth escalating
 * @param {boolean} options.enabled set false to not poll at all
 * @returns {{ data: any, loadedAt: number|null, failedAt: number|null, refresh: () => Promise<any> }}
 */
export default function usePolledData(load, { intervalMs, onError = () => {}, enabled = true } = {}) {
  const [data, setData] = useState(null);
  const [loadedAt, setLoadedAt] = useState(null);
  const [failedAt, setFailedAt] = useState(null);

  // Read inside the timer, so a new render does not restart the interval.
  const loadRef = useRef(load);
  loadRef.current = load;
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;
  const hasDataRef = useRef(false);
  const inFlightRef = useRef(false);
  const liveRef = useRef(true);

  const refresh = useCallback(() => {
    if (inFlightRef.current) {
      return Promise.resolve();
    }
    inFlightRef.current = true;
    return loadRef
      .current()
      .then((answer) => {
        if (liveRef.current) {
          hasDataRef.current = true;
          setData(answer);
          setLoadedAt(Date.now());
          setFailedAt(null);
        }
        return answer;
      })
      .catch((error) => {
        if (!liveRef.current) {
          return;
        }
        if (!hasDataRef.current || isFatal(error)) {
          onErrorRef.current(error);
          return;
        }
        // Logged because the page now says only "could not refresh"; the
        // reason is worth having when somebody looks.
        console.error(error);
        setFailedAt(Date.now());
      })
      .finally(() => {
        inFlightRef.current = false;
      });
  }, []);

  useEffect(() => {
    liveRef.current = true;
    return () => {
      liveRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (!enabled) {
      return undefined;
    }
    refresh();
    const timer = setInterval(() => {
      if (!document.hidden) {
        refresh();
      }
    }, intervalMs);
    return () => clearInterval(timer);
  }, [enabled, intervalMs, refresh]);

  return { data, loadedAt, failedAt, refresh };
}
