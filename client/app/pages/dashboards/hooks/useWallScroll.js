import { useEffect } from "react";

/** How often the scroll position is recomputed. */
const TICK_MS = 100;

/*
  The shape of one pass over a dashboard, as fractions of the period:
  rest at the top, travel down, rest at the bottom, travel back up. The rests
  are what make it readable -- a wall that never stops moving is a wall nobody
  reads -- and coming back up means the loop closes without a jump.
*/
const HOLD_TOP = 0.15;
const DOWN_UNTIL = 0.7;
const HOLD_BOTTOM = 0.85;

/**
 * How far down a dashboard taller than the screen should be at `phase`.
 *
 * Exported for its own test: the shape is the whole of the behaviour, and it
 * is far easier to check as arithmetic than by watching a page move.
 */
export function scrollFraction(phase) {
  if (phase <= HOLD_TOP) {
    return 0;
  }
  if (phase < DOWN_UNTIL) {
    return (phase - HOLD_TOP) / (DOWN_UNTIL - HOLD_TOP);
  }
  if (phase <= HOLD_BOTTOM) {
    return 1;
  }
  return 1 - (phase - HOLD_BOTTOM) / (1 - HOLD_BOTTOM);
}

/**
 * Walk a wall display down a dashboard that does not fit on the screen.
 *
 * Nobody is standing at a wall display to scroll it, so anything below the
 * fold is not merely awkward to reach -- it is never seen at all. On a 900px
 * screen the dashboard of every visualization had 15 of its 25 widgets below
 * it.
 *
 * It runs on the same period as the dashboard cycle, so a dashboard is back at
 * its top by the time it is replaced. A dashboard that fits does nothing at
 * all: no timer, no scrolling, no movement to distract anyone.
 */
export default function useWallScroll(periodSeconds, resetKey) {
  useEffect(() => {
    if (!(periodSeconds > 0)) {
      return undefined;
    }

    window.scrollTo(0, 0);

    const startedAt = Date.now();
    const periodMs = periodSeconds * 1000;

    const timer = setInterval(() => {
      // Measured every tick rather than once: widgets arrive after the page
      // does, and a dashboard's height is not settled until they have.
      const travel = document.documentElement.scrollHeight - window.innerHeight;
      if (travel <= 0) {
        return;
      }
      const phase = ((Date.now() - startedAt) % periodMs) / periodMs;
      window.scrollTo(0, Math.round(scrollFraction(phase) * travel));
    }, TICK_MS);

    return () => clearInterval(timer);
  }, [periodSeconds, resetKey]);
}
