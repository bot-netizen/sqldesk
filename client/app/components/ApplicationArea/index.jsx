import React, { useState, useEffect, useRef } from "react";
import routes from "@/services/routes";
import notification from "@/services/notification";
import { isChunkLoadError } from "@/lib/lazyPage";
import Router from "./Router";
import handleNavigationIntent from "./handleNavigationIntent";

/*
  An error nobody caught used to replace the entire application with an error
  page -- navigation, menus and all -- for as long as the tab lived, because
  the router it replaced was what listened for the next navigation. One stray
  error in a timer or a third-party script and the only way out was a reload,
  which a wall screen never gets.

  A render that throws is a different thing, and is still handled where it
  happens: the error boundary in `Router` shows the error in place of the
  page, inside the layout, and resets on the next navigation. What reaches
  the handler below is asynchronous -- a callback, an event handler, a script
  tag -- so the page it came from is usually still usable. It is reported and
  logged, and the application stays up.
*/

/** One report a minute, so a failing timer cannot bury the screen. */
export const REPORT_EVERY = 60 * 1000;

export default function ApplicationArea() {
  const [currentRoute, setCurrentRoute] = useState(null);
  const lastReportRef = useRef(null);

  useEffect(() => {
    if (currentRoute && currentRoute.title) {
      document.title = currentRoute.title;
    }
  }, [currentRoute]);

  useEffect(() => {
    function globalErrorHandler(event) {
      event.preventDefault();
      if (event.message === "Uncaught SyntaxError: Unexpected token '<'") {
        // if we see a javascript error on unexpected token where the unexpected token is '<', this usually means that a fallback html file (like index.html)
        // was served as content of script rather than the expected script, give a friendlier message in the console on what could be going on
        console.error(
          `[Uncaught SyntaxError: Unexpected token '<'] usually means that a fallback html file was returned from server rather than the expected script. Check that the server is properly serving the file ${event.filename}.`
        );
      }
      console.error(event.error || event.message);

      // A chunk that failed to load is already being retried, and reloads the
      // page if it has gone for good. Saying so here would be noise.
      if (isChunkLoadError(event.error)) {
        return;
      }

      const now = Date.now();
      if (lastReportRef.current !== null && now - lastReportRef.current < REPORT_EVERY) {
        return;
      }
      lastReportRef.current = now;
      notification.error(
        "Something on this page did not work",
        "The details are in the browser console. Reloading the page usually clears it."
      );
    }

    document.body.addEventListener("click", handleNavigationIntent, false);
    window.addEventListener("error", globalErrorHandler, false);

    return () => {
      document.body.removeEventListener("click", handleNavigationIntent, false);
      window.removeEventListener("error", globalErrorHandler, false);
    };
  }, []);

  return <Router routes={routes.items} onRouteChange={setCurrentRoute} />;
}
