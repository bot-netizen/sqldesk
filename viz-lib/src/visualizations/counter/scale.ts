import { isFinite } from "lodash";

/**
 * How far the number has to shrink to fit its box, or null when that cannot
 * be worked out yet.
 *
 * Null rather than a number matters: a container that has not been laid out
 * measures zero, and scaling to fit zero is `scale(0)` -- the number vanishes,
 * and stays vanished until something else happens to resize it. Leaving the
 * last good scale alone is always better than that.
 *
 * Kept apart from the renderer so it can be tested without loading ECharts.
 */
export default function getCounterScale(container: any): string | null {
  const inner = container && container.firstChild;
  if (!inner) {
    return null;
  }
  // offsetWidth/Height are layout sizes, so the transform already applied does
  // not feed into the next measurement.
  const { offsetWidth: boxWidth, offsetHeight: boxHeight } = container;
  const { offsetWidth: innerWidth, offsetHeight: innerHeight } = inner;
  if (boxWidth <= 0 || boxHeight <= 0 || innerWidth <= 0 || innerHeight <= 0) {
    return null;
  }
  const scale = Math.min(boxWidth / innerWidth, boxHeight / innerHeight);
  return isFinite(scale) && scale > 0 ? scale.toFixed(2) : null;
}
