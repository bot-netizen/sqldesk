import { each } from "lodash";

/*
  Which line the cursor is reading.

  On a chart with a dozen series the axis tooltip lists all twelve at the x
  under the pointer, and every one of them is drawn in the same weight. To
  find out which line you are actually looking at you match a colour swatch
  in the tooltip against a line on the plot, which is the work the chart was
  supposed to do for you.

  ECharts already knows how to make one series stand out -- every series is
  built with `emphasis: { focus: "series" }`, so highlighting one dims the
  rest. What it has no opinion about is *which* one, because an axis pointer
  is a position on the x axis and says nothing about how far up the cursor
  is. So: take the x from the axis pointer, the y from the cursor, and pick
  the series passing closest to it.
*/

/** A series' drawn position at the x under the pointer. */
export interface Candidate {
  seriesIndex: number;
  /** Pixels from the top of the canvas, or null where this series has no point here. */
  y: number | null;
}

/**
 * The series whose line passes nearest the cursor, or null when none does.
 *
 * `within` keeps a chart from highlighting a line the cursor is nowhere
 * near: without it, moving along the empty top of a plot would pick out
 * whichever series happened to be highest, which is a chart pointing at
 * something nobody asked about.
 */
export function nearestSeries(candidates: Candidate[], cursorY: number, within: number): number | null {
  let best: number | null = null;
  let bestGap = Infinity;
  each(candidates, ({ seriesIndex, y }) => {
    if (y === null || !isFinite(y)) {
      return;
    }
    const gap = Math.abs(y - cursorY);
    // Strictly closer, so where two lines overlap exactly the earlier series
    // wins and the highlight does not flicker between them as the cursor
    // moves along a shared stretch.
    if (gap < bestGap && gap <= within) {
      best = seriesIndex;
      bestGap = gap;
    }
  });
  return best;
}

/** How far from a line the cursor can be and still be reading it. */
export const FOLLOW_RADIUS = 40;

type Disposer = () => void;

/**
 * Make the nearest series follow the cursor on an ECharts instance.
 *
 * Returns a disposer. Safe to call on any chart: one without a cartesian
 * grid never fires `updateAxisPointer`, and one with a single series has
 * nothing to pick between, so both simply do nothing.
 */
export function followCursor(chart: any): Disposer {
  let cursorY: number | null = null;
  let lit: number | null = null;

  const zr = chart.getZr();

  const clear = () => {
    if (lit !== null) {
      chart.dispatchAction({ type: "downplay", seriesIndex: lit });
      lit = null;
    }
  };

  const onMove = (event: any) => {
    cursorY = event.offsetY;
  };

  const onLeave = () => {
    cursorY = null;
    clear();
  };

  const onPointer = (params: any) => {
    if (cursorY === null) {
      return;
    }
    const option = chart.getOption();
    const all = (option && option.series) || [];
    if (all.length < 2) {
      return;
    }

    // The x the pointer settled on, per axis. `axesInfo` carries the value
    // rather than the index, which is what a time or value axis needs --
    // only a category axis has indexes to speak of.
    const axis = (params.axesInfo || [])[0];
    if (!axis) {
      return;
    }

    const candidates: Candidate[] = [];
    each(all, (series: any, seriesIndex: number) => {
      const point = pointAt(series, axis);
      if (point === null) {
        candidates.push({ seriesIndex, y: null });
        return;
      }
      let pixel = null;
      try {
        pixel = chart.convertToPixel({ seriesIndex }, point);
      } catch (e) {
        pixel = null;
      }
      candidates.push({ seriesIndex, y: pixel ? pixel[1] : null });
    });

    const next = nearestSeries(candidates, cursorY, FOLLOW_RADIUS);
    if (next === lit) {
      return;
    }
    clear();
    if (next !== null) {
      chart.dispatchAction({ type: "highlight", seriesIndex: next });
      lit = next;
    }
  };

  zr.on("mousemove", onMove);
  zr.on("globalout", onLeave);
  chart.on("updateAxisPointer", onPointer);

  return () => {
    zr.off("mousemove", onMove);
    zr.off("globalout", onLeave);
    chart.off("updateAxisPointer", onPointer);
    clear();
  };
}

/**
 * This series' [x, y] where the pointer is, in data terms.
 *
 * Series data comes in both shapes: a pair per point on a time or value
 * axis, a bare number per point on a category axis. The axis pointer
 * reports a value in the first case and an index in the second, which is
 * why both are read here rather than one being normalised into the other.
 */
export function pointAt(series: any, axis: any): [any, any] | null {
  const data = series && series.data;
  if (!data || !data.length) {
    return null;
  }
  const index = axis.value !== undefined && axis.value !== null ? null : axis.dataIndex;
  if (index !== null && index !== undefined) {
    const point = data[index];
    if (point === undefined) {
      return null;
    }
    const y = Array.isArray(point) ? point[1] : point && point.value !== undefined ? point.value : point;
    return y === null || y === undefined ? null : [index, y];
  }

  // A pair series: find the point sitting at the pointer's x.
  for (let i = 0; i < data.length; i += 1) {
    const point = data[i];
    const pair = Array.isArray(point) ? point : point && Array.isArray(point.value) ? point.value : null;
    if (pair && Number(pair[0]) === Number(axis.value)) {
      return pair[1] === null || pair[1] === undefined ? null : [pair[0], pair[1]];
    }
  }
  return null;
}
