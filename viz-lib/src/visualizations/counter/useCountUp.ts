import { isFinite } from "lodash";
import { useEffect, useRef, useState } from "react";
import { formatCounterValue } from "./utils";

const DURATION = 450;

/** Ease-out cubic, matching the chart renderer's animationEasingUpdate. */
export function easeOut(t: number): number {
  return 1 - Math.pow(1 - t, 3);
}

export function interpolate(from: number, to: number, t: number): number {
  return from + (to - from) * easeOut(Math.min(Math.max(t, 0), 1));
}

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    !!window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

/**
 * Count from the previously displayed number to the new one.
 *
 * Returns a formatted string while a transition is running and `null` the rest
 * of the time, so the caller falls back to the value it already has. That keeps
 * the first render, non-numeric counters and reduced-motion users on exactly
 * the string they would have seen before.
 */
export default function useCountUp(value: number | null | undefined, options: any): string | null {
  const [display, setDisplay] = useState<string | null>(null);
  const previousRef = useRef<number | null>(null);

  // A counter with no rows reports no value at all, so anything that is not a
  // finite number counts as "nothing to animate from or to".
  const target = isFinite(value) ? (value as number) : null;

  useEffect(() => {
    const from = previousRef.current;
    previousRef.current = target;

    // Nothing to animate: no number, no previous number to start from, or no
    // actual change. Reduced motion opts out of the tween, not the value.
    if (target === null || from === null || from === target || prefersReducedMotion()) {
      setDisplay(null);
      return;
    }

    let frame = 0;
    const start = typeof performance !== "undefined" ? performance.now() : Date.now();
    const tick = (now: number) => {
      const elapsed = now - start;
      if (elapsed >= DURATION) {
        setDisplay(null); // settle on the caller's formatted value
        return;
      }
      setDisplay(formatCounterValue(interpolate(from, target, elapsed / DURATION), options));
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
