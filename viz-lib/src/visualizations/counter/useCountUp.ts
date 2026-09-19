import { isFinite } from "lodash";
import { useEffect, useRef, useState } from "react";
import { easeInOut, easeOut, ENTER_DURATION, UPDATE_DURATION } from "../shared/motion";
import { formatCounterValue } from "./utils";

export { easeOut };

export function interpolate(from: number, to: number, t: number, ease: (t: number) => number = easeOut): number {
  return from + (to - from) * ease(Math.min(Math.max(t, 0), 1));
}

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    !!window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

/**
 * Count up to the number: from zero when the counter first appears, from the
 * previous number when it changes.
 *
 * Returns a formatted string while a count is running and `null` the rest of
 * the time, so the caller falls back to the value it already has. Non-numeric
 * counters and reduced-motion users get the final string straight away.
 */
export default function useCountUp(value: number | null | undefined, options: any): string | null {
  // A counter with no rows reports no value at all, so anything that is not a
  // finite number counts as "nothing to animate from or to".
  const target = isFinite(value) ? (value as number) : null;

  // The first frame already shows zero, so the final number never flashes up
  // before the count starts.
  const [display, setDisplay] = useState<string | null>(() =>
    target !== null && target !== 0 && !prefersReducedMotion() ? formatCounterValue(0, options) : null
  );
  const previousRef = useRef<number | null>(null);
  const shownRef = useRef(false);

  useEffect(() => {
    const entering = !shownRef.current;
    shownRef.current = shownRef.current || target !== null;
    const from = entering ? 0 : previousRef.current;
    previousRef.current = target;

    // Nothing to animate: no number, nothing to start from, or no actual
    // change. Reduced motion opts out of the count, not the value.
    if (target === null || from === null || from === target || prefersReducedMotion()) {
      setDisplay(null);
      return;
    }

    const duration = entering ? ENTER_DURATION : UPDATE_DURATION;
    const ease = entering ? easeOut : easeInOut;
    let frame = 0;
    const start = typeof performance !== "undefined" ? performance.now() : Date.now();
    const tick = (now: number) => {
      const elapsed = now - start;
      if (elapsed >= duration) {
        setDisplay(null); // settle on the caller's formatted value
        return;
      }
      setDisplay(formatCounterValue(interpolate(from, target, elapsed / duration, ease), options));
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);

    return () => cancelAnimationFrame(frame);
    // Only the target drives the animation; re-running it on every options
    // identity change would restart the count mid-flight.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target]);

  return display;
}
