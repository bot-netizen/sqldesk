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

  "Finished" is deliberately conservative: the data is in, the fonts have
  loaded, and two frames have passed so the browser has actually painted.
  Waiting slightly too long costs a second; not waiting long enough costs the
  whole picture.
*/

export const SCREENSHOT_ATTRIBUTE = "data-rendered";

export function inScreenshotMode() {
  return has(location.search, "screenshot");
}

/**
 * Mark the document as drawn once `ready` is true.
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
    const markDrawn = () => {
      if (!cancelled) {
        document.documentElement.setAttribute(SCREENSHOT_ATTRIBUTE, "true");
      }
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
      requestAnimationFrame(() => requestAnimationFrame(markDrawn));
    });

    return () => {
      cancelled = true;
      document.documentElement.removeAttribute(SCREENSHOT_ATTRIBUTE);
    };
  }, [ready]);
}
