/**
 * How visualizations move, in one place.
 *
 * Enter: a widget's first draw grows from nothing -- bars rise from the axis,
 * gauges sweep up, numbers count up from zero -- at a pace people can follow
 * when a dashboard opens, rather than snapping into place.
 *
 * Update: new data moves from the old values to the new ones slowly enough to
 * see what changed. A dashboard that refreshes is only worth watching if the
 * change itself is visible.
 */
export const ENTER_DURATION = 1000;
export const UPDATE_DURATION = 1000;

export const ENTER_EASING = "cubicOut";
export const UPDATE_EASING = "cubicInOut";

/** The animation settings every ECharts option starts from. */
export const ECHARTS_MOTION = {
  animation: true,
  animationDuration: ENTER_DURATION,
  animationEasing: ENTER_EASING,
  animationDurationUpdate: UPDATE_DURATION,
  animationEasingUpdate: UPDATE_EASING,
};

/** Ease in and out, cubic: ECharts' "cubicInOut", for tweens drawn by hand. */
export function easeInOut(t: number): number {
  const c = Math.min(Math.max(t, 0), 1);
  return c < 0.5 ? 4 * c * c * c : 1 - Math.pow(-2 * c + 2, 3) / 2;
}

/** Ease out, cubic: ECharts' "cubicOut". */
export function easeOut(t: number): number {
  const c = Math.min(Math.max(t, 0), 1);
  return 1 - Math.pow(1 - c, 3);
}
