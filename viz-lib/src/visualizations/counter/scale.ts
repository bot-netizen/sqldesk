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
/**
 * A box smaller than this in either direction is not a layout, it is a box
 * mid-collapse -- a widget being dragged, a tab being switched. Fitting a
 * number to it means shrinking it to nothing.
 */
const MIN_MEASURABLE = 8;

/** Two decimal places, so never rounded all the way down to nothing. */
const MIN_SCALE = 0.01;

export default function getCounterScale(container: any): string | null {
  const inner = container && container.firstChild;
  if (!inner) {
    return null;
  }
  // offsetWidth/Height are layout sizes, so the transform already applied does
  // not feed into the next measurement.
  const { offsetWidth: boxWidth, offsetHeight: boxHeight } = container;
  const { offsetWidth: innerWidth, offsetHeight: innerHeight } = inner;
  if (boxWidth < MIN_MEASURABLE || boxHeight < MIN_MEASURABLE || innerWidth <= 0 || innerHeight <= 0) {
    return null;
  }
  const scale = Math.min(boxWidth / innerWidth, boxHeight / innerHeight);
  if (!isFinite(scale) || scale <= 0) {
    return null;
  }
  // toFixed rounds, and a ratio under 0.005 rounds to "0.00" -- which is
  // scale(0), and the number is gone.
  return Math.max(scale, MIN_SCALE).toFixed(2);
}
