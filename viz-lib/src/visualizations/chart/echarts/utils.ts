import { includes, isNil, mapValues } from "lodash";
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
