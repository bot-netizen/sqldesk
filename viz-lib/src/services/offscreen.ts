/*
  A chart nobody can see does not need to exist yet.

  Every ECharts visualization allocates a canvas the moment its container
  appears and runs its enter animation there, whether or not that part of the
  page has been scrolled to. On a twenty-widget dashboard that is twenty
  canvases and twenty animations for the four widgets somebody is looking at.
  Tab visibility was already handled; per-widget visibility was not.

  So creation waits for the widget to come near the viewport. `300px` of
  margin means it happens just before it is scrolled to rather than as it
  arrives, and once a chart exists it stays -- disposing on the way back out
  would trade a one-off cost for a repeated one, and lose the values a chart
  tweens from.

  The two cases where the viewport is the wrong question are the ones where
  the whole page is being turned into an image: the dashboard export and the
  alert screenshot renderer both capture a document taller than the window,
  and a widget that never drew is a blank rectangle in the picture. Those
  call `revealAllCharts` first.
*/

/** How early a chart is built, relative to the viewport. */
const MARGIN = "300px 0px";

let deferring = true;

/** Charts still waiting to be seen, so `revealAllCharts` can wake them. */
const waiting = new Set<() => void>();

/**
 * Draw every chart now and stop deferring the ones still to come.
 *
 * One way only: there is no re-arming. A page that has asked to be captured
 * is a page that wants everything drawn for as long as it lives.
 */
export function revealAllCharts(): void {
  deferring = false;
  // Copied, because waking one removes it from the set.
  Array.from(waiting).forEach((wake) => wake());
}

/** Whether charts are still being deferred. For tests and for callers that ask. */
export function isDeferringOffscreenCharts(): boolean {
  return deferring;
}

/**
 * Call `onScreen` once `element` is near the viewport -- or immediately, if
 * deferring is off or the browser has no `IntersectionObserver`.
 *
 * Returns a disposer. It is safe to call after `onScreen` has already run.
 */
export default function whenOnScreen(element: Element, onScreen: () => void): () => void {
  if (!deferring || typeof IntersectionObserver === "undefined") {
    onScreen();
    return () => {};
  }

  let observer: IntersectionObserver | null = null;
  // Once, whatever happens. A callback can already be queued when the
  // observer is disconnected, and `revealAllCharts` can arrive in the same
  // frame as the element scrolling in -- neither should build a second chart
  // on top of the first.
  let done = false;

  const stop = () => {
    done = true;
    if (observer) {
      observer.disconnect();
      observer = null;
    }
    waiting.delete(wake);
  };

  function wake() {
    if (done) {
      return;
    }
    stop();
    onScreen();
  }

  observer = new IntersectionObserver(
    (entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        wake();
      }
    },
    { rootMargin: MARGIN }
  );
  observer.observe(element);
  waiting.add(wake);

  return stop;
}

/** Test seam: put the module back to how it starts. */
export function resetOffscreenDeferralForTests(): void {
  deferring = true;
  waiting.clear();
}
