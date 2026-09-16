import { each, isNil } from "lodash";
import { cleanNumber, normalizeX, seriesId } from "./utils";

// Where the points sit relative to their box, as a fraction of the category
// band, and how far they spread. Plotly used pointpos -1.8 with jitter 0.3;
// these are the same idea expressed against the band rather than the box width.
const POINT_OFFSET = -0.26;
const POINT_JITTER = 0.09;

// ECharts "doesn't contain data processing modules, so the five statistic
// values should be calculated by yourself" -- Plotly derived them from the raw
// points. Everything in this file is that calculation.

export interface BoxStats {
  /** Whisker ends, not the data extremes: the furthest points inside the fences. */
  low: number;
  q1: number;
  median: number;
  q3: number;
  high: number;
  outliers: number[];
}

/**
 * Linear-interpolated quantile, the R type 7 definition.
 *
 * Plotly's box trace defaults to `quartilemethod: "linear"`, which is this one.
 * Picking a different definition would shift every existing box slightly, which
 * reads as the data having changed.
 */
export function quantile(sorted: number[], p: number): number {
  const n = sorted.length;
  if (n === 0) {
    return NaN;
  }
  if (n === 1) {
    return sorted[0];
  }
  const h = (n - 1) * p;
  const lower = Math.floor(h);
  const upper = Math.min(lower + 1, n - 1);
  return sorted[lower] + (h - lower) * (sorted[upper] - sorted[lower]);
}

/**
 * The five numbers plus the points outside the whiskers.
 *
 * Whiskers stop at the most extreme value within 1.5 IQR of the box -- Tukey's
 * rule, which is what Plotly draws and what ECharts' boxplot series expects.
 */
export function boxStats(values: number[]): BoxStats | null {
  const sorted = values.filter((v) => !isNil(v) && isFinite(v)).sort((a, b) => a - b);
  if (sorted.length === 0) {
    return null;
  }

  const q1 = quantile(sorted, 0.25);
  const median = quantile(sorted, 0.5);
  const q3 = quantile(sorted, 0.75);
  const iqr = q3 - q1;
  const lowerFence = q1 - 1.5 * iqr;
  const upperFence = q3 + 1.5 * iqr;

  const inliers = sorted.filter((v) => v >= lowerFence && v <= upperFence);
  const outliers = sorted.filter((v) => v < lowerFence || v > upperFence);

  return {
    // A box can be all outliers only if the fences are degenerate; fall back to
    // the data range rather than drawing a box with no whiskers.
    low: inliers.length > 0 ? inliers[0] : sorted[0],
    q1,
    median,
    q3,
    high: inliers.length > 0 ? inliers[inliers.length - 1] : sorted[sorted.length - 1],
    outliers,
  };
}

/**
 * Spread overlapping points so a stack of equal values reads as a stack.
 *
 * Derived from the point's own index rather than Math.random, so the same data
 * draws identically every render -- a random offset would make the points crawl
 * on each update, which is precisely the opposite of animating a change.
 */
function jitterFor(index: number): number {
  // Golden-ratio stepping: successive indices land far apart, and the sequence
  // fills the interval evenly rather than clustering.
  const fraction = (index * 0.618033988749895) % 1;
  return (fraction - 0.5) * 2 * POINT_JITTER;
}

/**
 * Points beside a box, placed in pixels.
 *
 * A category axis snaps fractional positions back to the category, so a scatter
 * series cannot be nudged sideways at all -- every point would land on the
 * centre line, hidden behind the box. Drawing them as a custom series is the
 * only way to offset and spread them.
 */
function renderPoint(params: any, api: any) {
  const band = api.size([1, 0])[0];
  const centre = api.coord([api.value(0), api.value(1)]);
  const offset = (api.value(2) + api.value(3)) * band;
  return {
    type: "circle",
    transition: ["shape"],
    shape: { cx: centre[0] + offset, cy: centre[1], r: 2.5 },
    style: api.style({ fill: api.visual("color"), stroke: undefined }),
  };
}

/** Collect the raw y values behind each category, per series. */
function groupByCategory(points: any[], xAxisType: string) {
  const groups = new Map<any, number[]>();
  each(points, (point: any) => {
    const x = normalizeX(point.x, xAxisType);
    const y = cleanNumber(point.y);
    if (isNil(x) || isNil(y)) {
      return;
    }
    const bucket = groups.get(x);
    if (bucket) {
      bucket.push(y);
    } else {
      groups.set(x, [y]);
    }
  });
  return groups;
}

/**
 * One boxplot series per data series, plus a scatter series carrying the points
 * drawn beside it. ECharts has no equivalent of `boxpoints`, so the outliers --
 * or every point, under "Show All Points" -- are their own series.
 */
export function buildBoxSeries(
  chartData: any[],
  options: any,
  xAxisType: string,
  categories: any[],
  colorFor: (name: string, index: number) => string
) {
  const showAllPoints = !!options.showpoints;
  const series: any[] = [];

  each(chartData, (dataSeries: any, index: number) => {
    const color = colorFor(dataSeries.name, index);
    const groups = groupByCategory(dataSeries.data, xAxisType);

    const boxes: any[] = [];
    const points: any[] = [];

    each(categories, (category, categoryIndex) => {
      const values = groups.get(category);
      const stats = values ? boxStats(values) : null;
      if (!stats) {
        // ECharts skips a null entry, which keeps every series aligned to the
        // same category positions.
        boxes.push(null);
        return;
      }
      boxes.push([stats.low, stats.q1, stats.median, stats.q3, stats.high]);
      // Outliers belong on the box's own centre line, the way Plotly drew them;
      // "Show All Points" moves the whole cloud beside the box instead, so the
      // box stays readable underneath.
      each(showAllPoints ? values : stats.outliers, (value, pointIndex: any) =>
        points.push([
          categoryIndex,
          value,
          showAllPoints ? POINT_OFFSET : 0,
          showAllPoints ? jitterFor(points.length + pointIndex) : 0,
        ])
      );
    });

    series.push({
      id: seriesId(dataSeries.name),
      name: dataSeries.name,
      type: "boxplot",
      data: boxes,
      itemStyle: { color: "transparent", borderColor: color, borderWidth: 1.5 },
      emphasis: { focus: "series", itemStyle: { borderWidth: 2 } },
    });

    if (points.length > 0) {
      series.push({
        id: `${seriesId(dataSeries.name)}:points`,
        name: dataSeries.name,
        type: "custom",
        data: points,
        renderItem: renderPoint,
        itemStyle: { color },
        // The points belong to their box; listing them separately would show
        // every series name twice.
        legendHoverLink: false,
        silent: true,
        tooltip: { show: false },
        z: 3,
      });
    }
  });

  return series;
}
