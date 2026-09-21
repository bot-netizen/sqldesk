import { useEffect, useRef, useState } from "react";

/** How often the progress bar moves. Not how often the dashboard changes. */
const TICK_MS = 250;

/**
 * Which dashboard a wall is showing, and how far through its turn it is.
 *
 * One dashboard means it never moves and there is no progress to show; the
 * timer is not started at all, so a single-dashboard wall does no work
 * between refreshes.
 */
export default function useDashboardCycle(tokens, dwellSeconds) {
  const [current, setCurrent] = useState(0);
  const [progress, setProgress] = useState(0);
  const startedAt = useRef(Date.now());

  const count = tokens.length;

  useEffect(() => {
    if (count <= 1 || !(dwellSeconds > 0)) {
      setCurrent(0);
      setProgress(0);
      return undefined;
    }

    startedAt.current = Date.now();
    const dwellMs = dwellSeconds * 1000;

    // Driven off the clock rather than by counting ticks: a wall display is
    // left running for weeks, and a tab that is throttled or briefly asleep
    // would otherwise drift further behind every hour.
    const timer = setInterval(() => {
      const elapsed = Date.now() - startedAt.current;
      if (elapsed >= dwellMs) {
        startedAt.current = Date.now();
        setProgress(0);
        setCurrent((index) => (index + 1) % count);
      } else {
        setProgress(elapsed / dwellMs);
      }
    }, TICK_MS);

    return () => clearInterval(timer);
  }, [count, dwellSeconds]);

  return { current, progress };
}
