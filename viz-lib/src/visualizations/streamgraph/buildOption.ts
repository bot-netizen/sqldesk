import moment from "moment";
import { each, map, sortBy } from "lodash";
import escapeHtml from "@/lib/escapeHtml";
import { ECHARTS_MOTION } from "@/visualizations/shared/motion";
import { NO_ROWS } from "@/visualizations/shared/components/Problem";
import { createNumberFormatter } from "@/lib/value-format";
import { timeAxisFormatter, timeAxisInterval, timeAxisTicks, timePointerFormatter } from "../chart/echarts/utils";
import { StreamgraphOptions } from "./getOptions";

/*
  A stacked area with no baseline.

  A stacked bar answers "how much, broken down"; a streamgraph answers "how
  is the mix changing", and it answers it better because nothing is pinned
  to zero -- every band is free to be read as its own shape rather than as
  the gap between two lines that are both moving.

  The cost is that you cannot read an absolute value off it, which is why
  the tooltip carries the numbers. That is the trade, and it is the right
  one for the question this chart is for.
*/

export interface BuiltStreamgraph {
  option: any;
  signature: string;
  problem: string | null;
}

/** A point on the river: when, how much, and which band. */
export type RiverPoint = [string | number, number, string];

/**
 * Why this cannot be drawn, in words -- or null.
 *
 * Three columns have to be chosen and they have to be three *different*
 * columns: picking the same one for the axis and the band draws a single
 * band and reads as a broken chart rather than a misconfigured one.
 */
export function problemWith(data: any, options: StreamgraphOptions): string | null {
  if (!data || !data.rows || data.rows.length === 0) {
    return NO_ROWS;
  }
  if (!options.xColumn || !options.seriesColumn || !options.valueColumn) {
    return "Choose a column for the axis, one for the bands and one for the value.";
  }
  if (options.xColumn === options.seriesColumn) {
    return "The axis and the bands need to be different columns.";
  }
  return null;
}

/**
 * A date becomes milliseconds; anything else stays the label it was.
 *
 * Milliseconds rather than a formatted string, because a zone-less string
 * is read differently by whoever reads it: ECharts takes "2026-08-10
 * 00:00:00" as UTC under `useUTC`, and `Date.parse` takes it as local, so
 * the ticks were computed four hours away from where they were drawn. A
 * number means the same instant to everybody.
 */
export function axisValue(value: any): string | number {
  if (moment.isMoment(value)) {
    return value.isValid() ? value.valueOf() : String(value);
  }
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? "" : value.getTime();
  }
  return value === null || value === undefined ? "" : String(value);
}

/**
 * Rows into river points.
 *
 * Summed per (x, band), because two rows at the same point in the same band
 * are one thicker band and not two bands sharing a name -- ECharts would
 * draw the second over the first and lose it.
 */
export function riverPoints(rows: any[], options: StreamgraphOptions): RiverPoint[] {
  const totals = new Map<string, RiverPoint>();
  each(rows, (row) => {
    const x = axisValue(row[options.xColumn]);
    const band = String(row[options.seriesColumn] ?? "");
    const raw = Number(row[options.valueColumn]);
    const value = Number.isFinite(raw) ? raw : 0;
    const key = `${x}\u0000${band}`;
    const existing = totals.get(key);
    if (existing) {
      existing[1] += value;
    } else {
      totals.set(key, [x, value, band]);
    }
  });
  // Ordered along the axis: ECharts draws the river in the order it is
  // given, so unsorted rows come out as a scribble.
  return sortBy(Array.from(totals.values()), [(point) => point[0], (point) => point[2]]);
}

/** The bands, in first-seen order, which is what the legend lists. */
export function bandsIn(points: RiverPoint[]): string[] {
  const seen: string[] = [];
  each(points, ([, , band]) => {
    if (!seen.includes(band)) {
      seen.push(band);
    }
  });
  return seen;
}

export default function buildOption(data: any, rawOptions: StreamgraphOptions): BuiltStreamgraph {
  const problem = problemWith(data, rawOptions);
  if (problem) {
    return { option: { series: [] }, signature: "invalid", problem };
  }

  const points = riverPoints(data.rows, rawOptions);
  const bands = bandsIn(points);
  const format = createNumberFormatter(rawOptions.valueFormat);

  // The same treatment the chart's time axis gets, for the same reasons:
  // values are parsed as UTC and must be rendered as UTC or every daily
  // point is labelled a day early, and ECharts' own labels are a run of
  // bare numbers. See chart/echarts/utils.
  const first = points.length && typeof points[0][0] === "number" ? (points[0][0] as number) : NaN;
  const last =
    points.length && typeof points[points.length - 1][0] === "number" ? (points[points.length - 1][0] as number) : NaN;
  const span = Number.isFinite(first) && Number.isFinite(last) ? Math.max(0, last - first) : 0;
  const interval = timeAxisInterval(span);
  const ticks = interval && Number.isFinite(first) ? timeAxisTicks(first, last, interval) : [];
  const formatTime = timeAxisFormatter(span);
  const formatPointerTime = timePointerFormatter(span);

  const option = {
    ...ECHARTS_MOTION,
    useUTC: true,
    tooltip: {
      trigger: "axis",
      confine: true,
      axisPointer: { type: "line", lineStyle: { type: "dotted", width: 1 } },
    },
    legend: rawOptions.showLegend
      ? { show: true, type: "scroll", bottom: 0, icon: "roundRect", data: bands }
      : { show: false },
    singleAxis: {
      type: "time",
      top: 10,
      bottom: rawOptions.showLegend ? 46 : 20,
      left: 10,
      right: 10,
      axisLabel: { hideOverlap: true, formatter: formatTime, ...(ticks.length ? { customValues: ticks } : {}) },
      ...(ticks.length ? { axisTick: { show: true, customValues: ticks } } : {}),
      splitLine: { show: false },
    },
    series: [
      {
        id: "streamgraph",
        type: "themeRiver",
        data: points,
        emphasis: { focus: "series" },
        label: { show: false },
        // The bands only read as bands if they are told apart at a glance;
        // a hairline between them does that without adding a legend lookup.
        itemStyle: { borderColor: "#fff", borderWidth: 0.5 },
        tooltip: {
          formatter: (params: any) => {
            const point = params.value || [];
            const when = typeof point[0] === "number" ? formatPointerTime(point[0]) : String(point[0]);
            return `${escapeHtml(when)}<br/>${escapeHtml(String(point[2]))}: ${escapeHtml(format(point[1]))}`;
          },
        },
      },
    ],
  };

  // The bands are the shape: the same bands with new weights can tween, a
  // different set has to be rebuilt.
  return { option, signature: JSON.stringify(bands), problem: null };
}
