import { useEffect } from "react";

/**
 * Put the page into the dark wall theme, and take it out again on the way.
 *
 * The attribute goes on `<html>`, not on a wrapper, because that is where the
 * visualizations look. `uiColor()` in viz-lib reads the tokens off
 * `document.documentElement` at the moment it draws a chart, so setting it
 * here is what makes every visualization come out dark without any of them
 * knowing this mode exists.
 *
 * It is set in a layout effect's place -- before paint would be better still,
 * but the dashboard's own fetch means nothing draws for a beat anyway, and
 * the charts that read these tokens are the last thing to appear.
 */
export default function useWallTheme(enabled = true) {
  useEffect(() => {
    if (!enabled || typeof document === "undefined") {
      return undefined;
    }
    const root = document.documentElement;
    const previous = root.getAttribute("data-theme");
    root.setAttribute("data-theme", "wall");
    // The wall page has no navbar and no scrollbar chrome of its own; the
    // class is what the stylesheet hangs the rest of that on.
    document.body.classList.add("wall-display");

    return () => {
      if (previous === null) {
        root.removeAttribute("data-theme");
      } else {
        root.setAttribute("data-theme", previous);
      }
      document.body.classList.remove("wall-display");
    };
  }, [enabled]);
}
