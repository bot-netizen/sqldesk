import { useEffect } from "react";
import { has } from "lodash";
import location from "@/services/location";

/*
  `?screenshot=1`: the page is being photographed, not read.

  Two things follow from that. The chrome goes, because a picture of a chart
  should be a chart. And the page has to say when it has finished drawing,
  because the renderer on the other side has no way to know: without a signal
  the usual result is a photograph of a loading spinner. Superset's own
  documentation describes checking captures for blank content afterwards,
  which is what you are left doing when the page never says.

  "Finished" has to mean *settled*, not *data has arrived*. The first version
  waited for the data and two animation frames, and produced a counter whose
  sparkline was a 90px sliver in the corner of a box 1350px wide: ECharts had
  drawn itself at the size its container had before the flex layout resolved,
  and viz-lib's resize watcher -- which polls at 100ms -- had not yet told it
  to grow. The picture was of a real moment, just not a moment anyone would
  recognise.

  So the page now waits for its own layout to stop moving: it samples the
  things that change when a chart resizes and only says "drawn" once two
  consecutive samples agree. That naturally covers the polling watcher, web
  fonts reflowing text, and anything else that settles late, without guessing
  at a sleep long enough to cover all three.
*/

export const SCREENSHOT_ATTRIBUTE = "data-rendered";

/** How often to look for movement. Longer than viz-lib's 100ms resize poll. */
const SAMPLE_MS = 150;

/** Two matching samples means settled. */
const STABLE_SAMPLES = 2;

/**
 * Give up waiting and take the picture anyway.
 *
 * A page that never settles -- a live dashboard ticking every second, an
 * animation that does not end -- must still be photographed. A slightly early
 * picture beats a timeout and no picture at all.
 */
const DEADLINE_MS = 10000;

export function inScreenshotMode() {
  return has(location.search, "screenshot");
}

/**
 * What the page looks like right now, as a string.
 *
 * Canvas dimensions are the tell: every chart here draws into one, and a
 * chart that is still growing changes them. The document height catches
 * everything else -- a table paginating in, an image loading, text reflowing
 * when a font arrives.
 */
function layoutFingerprint() {
  const canvases = Array.prototype.map
    .call(document.querySelectorAll("canvas"), (canvas) => `${canvas.width}x${canvas.height}`)
    .join(",");
  return `${document.documentElement.scrollHeight}|${document.documentElement.scrollWidth}|${canvases}`;
}

/**
 * Mark the document as drawn once `ready` is true and the page has settled.
 *
 * Set on <html> rather than on any one element so the renderer's selector
 * does not depend on a page's markup.
 */
export default function useScreenshotMode(ready) {
  useEffect(() => {
    if (!inScreenshotMode() || !ready) {
      return undefined;
    }

    let cancelled = false;
    let timer = null;

    const markDrawn = () => {
      if (!cancelled) {
        document.documentElement.setAttribute(SCREENSHOT_ATTRIBUTE, "true");
      }
    };

    const waitForStillness = (previous, matches, startedAt) => {
      if (cancelled) {
        return;
      }

      const current = layoutFingerprint();
      const agreed = current === previous ? matches + 1 : 0;

      if (agreed >= STABLE_SAMPLES || Date.now() - startedAt > DEADLINE_MS) {
        markDrawn();
        return;
      }

      timer = setTimeout(() => waitForStillness(current, agreed, startedAt), SAMPLE_MS);
    };

    // `document.fonts` is missing in older browsers and in jsdom; a page that
    // cannot ask about fonts should still say it is drawn. The feature check
    // is the whole line, which the compat rule cannot see -- and the browser
    // doing the photographing is a current Chromium in any case.
    // eslint-disable-next-line compat/compat
    const fonts = document.fonts ? document.fonts.ready : Promise.resolve();

    fonts.then(() => {
      if (cancelled) {
        return;
      }
      waitForStillness(null, 0, Date.now());
    });

    return () => {
      cancelled = true;
      clearTimeout(timer);
      document.documentElement.removeAttribute(SCREENSHOT_ATTRIBUTE);
    };
  }, [ready]);
}
