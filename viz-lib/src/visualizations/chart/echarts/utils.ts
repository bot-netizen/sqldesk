import { each, includes, isNil, mapValues } from "lodash";
import moment from "moment";

// Every chart type the renderer can draw. Plotly used to catch anything absent
// from this list; now that it is gone, an unsupported type has nowhere to go, so
// it is corrected on the way in instead -- see normalizeSeriesTypes.
export const ECHARTS_SERIES_TYPES = ["column", "line", "area", "scatter", "pie", "bubble", "heatmap", "box"];

export const DEFAULT_SERIES_TYPE = "column";

// Types that decide the shape of the whole chart rather than of one series: a
// pie has no axes, a heatmap addresses cells by index, a box aggregates rows
// into distributions. The renderer branches on the global setting for these, so
// mixing one into an otherwise cartesian chart has no meaning.
const WHOLE_CHART_TYPES = ["pie", "heatmap", "box"];

function isDrawable(type: any): boolean {
  return includes(ECHARTS_SERIES_TYPES, type);
}

/**
 * Correct the series types on a saved chart so it can always be drawn.
 *
 * Saved visualizations outlive the code that wrote them. A chart saved as
 * `custom` held JavaScript written against the Plotly API; there is nothing left
 * to run it, and "custom" happens to also name an ECharts series, so leaving it
 * alone would draw an empty canvas rather than fail loudly. A per-series
 * override can likewise name a type that no longer exists, or a whole-chart type
 * that cannot be mixed into a cartesian chart.
 *
 * Everything unrecognised becomes a column: readable, obviously not what the
 * author chose, and recoverable by editing the visualization.
 */
export function normalizeSeriesTypes(options: any): any {
  const globalSeriesType = isDrawable(options.globalSeriesType) ? options.globalSeriesType : DEFAULT_SERIES_TYPE;
  const wholeChart = includes(WHOLE_CHART_TYPES, globalSeriesType);

  const seriesOptions = mapValues(options.seriesOptions || {}, (series: any) => {
    const type = series && series.type;
    if (!type || type === globalSeriesType) {
      return series;
    }
    // A whole-chart type on either side means the override cannot stand: the
    // renderer reads the global setting, not this one.
    const usable = wholeChart || includes(WHOLE_CHART_TYPES, type) ? false : isDrawable(type);
    return usable ? series : { ...series, type: globalSeriesType };
  });

  return { ...options, globalSeriesType, seriesOptions };
}

/**
 * Coerce a value to a number, or null when it is not one.
 *
 * Deliberately not the helper in `plotly/utils.ts`: that one calls
 * `plotly.js/src/lib/clean_number`, so reusing it would pull Plotly into the
 * ECharts path and defeat the point of the migration.
 */
export function cleanNumber(value: any): number | null {
  if (isNil(value) || value === "") {
    return null;
  }
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : null;
  }
  if (typeof value === "string") {
    // Thousands separators and stray whitespace are common in query output.
    const trimmed = value.trim().replace(/[\s,]/g, "");
    if (trimmed === "") {
      return null;
    }
    const parsed = Number(trimmed);
    return Number.isFinite(parsed) ? parsed : null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/** ECharts axis type for one of our saved axis settings. */
export function echartsAxisType(axisType: any, values: any[] = []): "category" | "value" | "time" | "log" {
  switch (axisType) {
    case "datetime":
      return "time";
    case "logarithmic":
      return "log";
    case "linear":
      return "value";
    case "category":
      return "category";
    default:
      // "-" means "decide for me", which Plotly did by inspection, and it is
      // what the editor saves unless someone changes it. Dates are checked
      // first: a datetime column arrives as moments, and a moment converts to
      // a number -- its epoch milliseconds -- so asking "are these numbers?"
      // first put every time series on a numeric axis running from 0 to
      // 1.8 trillion, with all its points piled up at the right-hand end.
      if (values.length === 0) {
        return "category";
      }
      if (values.every(isDateLike)) {
        return "time";
      }
      return values.every((v) => cleanNumber(v) !== null) ? "value" : "category";
  }
}

/**
 * A point in time: a moment, a Date, or an ISO 8601 date or date-time string
 * (what a data source that types every column as text hands over). A bare
 * number is not one, even though moment would read it as milliseconds.
 */
export function isDateLike(value: any): boolean {
  if (moment.isMoment(value)) {
    return value.isValid();
  }
  if (value instanceof Date) {
    return !isNaN(value.getTime());
  }
  return (
    typeof value === "string" && /^\d{4}-\d{2}-\d{2}/.test(value) && moment(value, moment.ISO_8601, true).isValid()
  );
}

/**
 * Normalise an x value for the chosen axis.
 *
 * Time axes get epoch milliseconds rather than a formatted string: ECharts
 * parses strings with `Date`, which disagrees across browsers for anything but
 * ISO 8601, and silently drops the points it cannot read.
 */
export function normalizeX(value: any, axisType: string): any {
  if (axisType === "time") {
    // Almost always a moment already: `query-result` converts every timestamp
    // cell on the way in, and handing one back to `moment.utc` only clones
    // it. Measured at 9ms per 20,000 points, which is one chart.
    if (moment.isMoment(value)) {
      return value.isValid() ? value.valueOf() : null;
    }
    if (value instanceof Date) {
      return isNaN(value.getTime()) ? null : value.getTime();
    }
    const parsed = moment.utc(value);
    return parsed.isValid() ? parsed.valueOf() : null;
  }
  if (axisType === "value" || axisType === "log") {
    return cleanNumber(value);
  }
  if (moment.isMoment(value)) {
    return value.format("YYYY-MM-DD HH:mm:ss");
  }
  return isNil(value) ? null : String(value);
}

/** Which y axis a series belongs to. Mirrors the existing Plotly behaviour. */
export function getSeriesAxisIndex(seriesName: string, options: any): 0 | 1 {
  const seriesOptions = options.seriesOptions[seriesName] || { type: options.globalSeriesType };
  if (seriesOptions.yAxis === 1 && (!options.series.stacking || seriesOptions.type === "line")) {
    return 1;
  }
  return 0;
}

/**
 * A series identity that survives a data refresh.
 *
 * ECharts matches series between `setOption` calls by `id`, then `name`, then
 * array position. Our series come out of query columns in whatever order the
 * rows arrive, so without an explicit id a reordered result reads as "delete
 * one series, create another" and the chart jumps instead of animating.
 */
export function seriesId(name: string): string {
  return `series:${name}`;
}

const MINUTE = 60000;
const HOUR = 3600000;
const DAY = 86400000;

/**
 * How a timestamp on the x axis should read, given how much time the chart
 * covers.
 *
 * ECharts' own time axis labels a run of days as bare numbers -- "15", "22",
 * "29" -- and prints the month only where it turns. On a three-month chart
 * that is a row of numbers with two words in it, and nobody can say what
 * "22" is without counting back to the nearest month name. These say the
 * month on every label and let `hideOverlap` drop whichever will not fit,
 * which costs a few labels and leaves every surviving one readable on its
 * own.
 *
 * Within a day the dates are the thing that goes missing instead: a row of
 * "06:00 18:00 06:00 18:00" with a lone "3" in it. Midnight carries the date
 * here, so each run of times is anchored to the day it belongs to.
 */
export function timeAxisFormatter(span: number): (value: any) => string {
  /*
    A label has to be at least as fine as the ticks it sits under.

    These used to be chosen from the span alone, while the ticks are spaced
    by `timeAxisInterval` -- and the two disagreed wherever a span's ticks
    fall closer together than its labels can say. Found in the streams
    picture taken for the website: three minutes of a topic, ticks every
    fifteen seconds, and "23:24 23:24 23:24 23:24". The same happened to six-
    hour ticks on a four-day chart ("6 Nov" four times), fortnightly ticks
    under "MMM YYYY", and half-yearly ones under "YYYY".
  */
  const step = timeAxisInterval(span) ?? Infinity;
  if (span >= 3 * 365 * DAY && step >= 365 * DAY) {
    return (value) => moment.utc(value).format("YYYY");
  }
  // Quarters at the finest: a 28-day step lands twice in a 31-day month.
  if (span >= 120 * DAY && step >= 91 * DAY) {
    return (value) => moment.utc(value).format("MMM YYYY");
  }
  if (span >= 3 * DAY && step >= DAY) {
    return (value) => moment.utc(value).format("D MMM");
  }
  // Down to here from a multi-day span whose ticks are hours apart, too.
  if (span >= 2 * HOUR) {
    return (value) => {
      const at = moment.utc(value);
      return at.hour() === 0 && at.minute() === 0 ? at.format("D MMM") : at.format("HH:mm");
    };
  }
  // Seconds only once they are what distinguishes one tick from the next.
  // On a chart whose ticks are minutes apart they are three characters of
  // ":00" on every label.
  if (step >= MINUTE) {
    return (value) => moment.utc(value).format("HH:mm");
  }
  return (value) => moment.utc(value).format("HH:mm:ss");
}

/**
 * The same timestamp where there is room to be unambiguous: the label on the
 * axis under the pointer, and the heading above the tooltip.
 *
 * Fuller than the axis, because it is one label rather than thirty, and it is
 * the one a person reads when they want to know exactly which point they are
 * looking at. A day gets its weekday -- "is that bar a Sunday?" is most of
 * why anybody hovers a daily chart -- and no time of day, which on daily
 * buckets is a midnight that means nothing and reads as precision that is
 * not there.
 */
export function timePointerFormatter(span: number): (value: any) => string {
  if (span >= 3 * 365 * DAY) {
    return (value) => moment.utc(value).format("MMM YYYY");
  }
  if (span >= 3 * DAY) {
    return (value) => moment.utc(value).format("ddd D MMM YYYY");
  }
  if (span >= 2 * HOUR) {
    return (value) => moment.utc(value).format("ddd D MMM, HH:mm");
  }
  return (value) => moment.utc(value).format("ddd D MMM, HH:mm:ss");
}

/** The time a chart covers, in milliseconds, or 0 when it covers no time. */
export function timeSpan(chartData: any[]): number {
  let low = Infinity;
  let high = -Infinity;
  each(chartData, (series: any) =>
    each(series.data, (point: any) => {
      const x = normalizeX(point.x, "time");
      if (!isNil(x)) {
        low = Math.min(low, x);
        high = Math.max(high, x);
      }
    })
  );
  return high > low ? high - low : 0;
}

/**
 * How far apart the ticks on a time axis should be.
 *
 * Left to itself ECharts anchors one rhythm to the data's start and another
 * to each month, and draws both: a 90-day axis came out "15, 22, 29, 5, 8,
 * 15, 22, 29, 6, 8" -- mostly weekly, with a three-day step wherever a
 * month began. Months are not a whole number of weeks, so the two rhythms
 * cannot agree, and nothing about the result says which gap is which.
 *
 * Choosing the step ourselves makes every gap the same. The candidates are
 * durations people actually think in, and the smallest one that keeps the
 * axis under `most` labels wins -- so the step grows with the range rather
 * than the label count growing without limit.
 */
const TICK_STEPS = [
  1000,
  5 * 1000,
  15 * 1000,
  30 * 1000,
  MINUTE,
  5 * MINUTE,
  15 * MINUTE,
  30 * MINUTE,
  HOUR,
  3 * HOUR,
  6 * HOUR,
  12 * HOUR,
  DAY,
  2 * DAY,
  7 * DAY,
  14 * DAY,
  28 * DAY,
  91 * DAY,
  182 * DAY,
  365 * DAY,
];

export function timeAxisInterval(span: number, most = 13): number | undefined {
  if (!span || span <= 0) {
    return undefined;
  }
  const step = TICK_STEPS.find((candidate) => span / candidate <= most);
  // Past a decade the steps run out; ECharts' own choice of year boundaries
  // is regular enough once a tick is a year or more apart.
  return step === undefined ? undefined : step;
}

/**
 * The exact timestamps to put ticks on.
 *
 * `minInterval`/`maxInterval` are a request, not an instruction: ECharts'
 * time axis still snaps to calendar boundaries, and a month is not a whole
 * number of days-times-anything, so asking for a four-day step produced
 * "13, 17, 21, 25 Aug, 5 Sep" -- four days apart until the month turned
 * and then eleven. Handing it the positions outright is the only way the
 * gaps come out equal, and ECharts has taken `customValues` since 5.5.
 *
 * Anchored to the first point rather than to a round date, so the left end
 * of the axis is always labelled; an axis whose first tick floats several
 * days in looks like the data starts later than it does.
 */
export function timeAxisTicks(from: number, to: number, interval: number): number[] {
  if (!interval || interval <= 0 || !(to > from)) {
    return [];
  }
  const ticks: number[] = [];
  // A guard rather than a limit anybody should reach: a pathological
  // interval against a long span would otherwise build an endless array.
  for (let at = from; at <= to && ticks.length < 400; at += interval) {
    ticks.push(at);
  }
  return ticks;
}
