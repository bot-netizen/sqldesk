/*
  Some errors reach `window.onerror` that mean nothing to the person using the
  page, and telling them about one is worse than saying nothing.

  ResizeObserver fires "loop completed with undelivered notifications" whenever
  a resize callback resizes something itself. That is exactly what
  `useElementSize` does -- it measures a widget so a visualization can scale
  its text to the space it has -- so every counter, gauge and sankey on a
  dashboard that reflows can produce one. The browser has already settled the
  layout by the time it says so. There is nothing to fix.

  It matters here because of how it arrives: an ErrorEvent carrying a `message`
  and no `error` object at all. A check that only looks at `event.error` never
  sees it, so it fell through to the report and put "Something on this page did
  not work" in front of people whose page was working perfectly. Reloading
  "fixed" it only because the warning does not fire twice on a settled layout.

  Safari and older Chrome say "loop limit exceeded" for the same condition.
*/
const BENIGN = /ResizeObserver loop (?:completed with undelivered notifications|limit exceeded)/i;

/**
 * Noise the browser reports that the person reading the page cannot act on.
 *
 * Takes the whole ErrorEvent rather than its `error`, because the errors worth
 * suppressing here are the ones that do not carry an `error` at all.
 *
 * @param {{ error?: any, message?: string }} event an ErrorEvent, or anything shaped like one
 */
export default function isBenignBrowserNoise(event) {
  if (!event) {
    return false;
  }
  const error = event.error;
  const text = (error && (error.message || error)) || event.message || "";
  return BENIGN.test(String(text));
}
