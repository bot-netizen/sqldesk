import moment from "moment";
import { resolveColor, toNumber } from "../../shared/valueOptions";

/*
  What 0.4 adds to cartesian charts:

  - Reference lines: a goal or a limit at a fixed value, the average, minimum
    or maximum of a series, or a marker at a point along the x axis.
  - Reference bands: a shaded range on the value axis, for "normal" or
    "warning" zones.
  - A rolling window, so a chart over a live query shows the last N points or
    minutes and slides as new ones arrive, instead of squeezing ever more in.
  - Zoom, with a slider, the mouse wheel, or both.
*/

export type ReferenceKind = "value" | "average" | "min" | "max" | "x";

export interface ReferenceLine {
  kind: ReferenceKind;
  /** A number for "value", an x position for "x"; unused for the statistics. */
  value: number | string | null;
  /** Which series a statistic is taken from. Empty means the first. */
  series: string;
  label: string;
  color: string;
  style: "dashed" | "solid";
}

export interface ReferenceBand {
  /** Null runs the band to the end of the axis. */
  from: number | null;
  to: number | null;
  label: string;
  color: string;
}

export type WindowMode = "all" | "points" | "minutes";

export interface ChartWindow {
  mode: WindowMode;
  points: number;
  minutes: number;
}

export type ZoomMode = "none" | "slider" | "inside" | "both";

export const DEFAULT_WINDOW: ChartWindow = { mode: "all", points: 50, minutes: 60 };

const REFERENCE_SERIES_ID = "series:reference";

function timeOf(x: any): number | null {
  if (x === null || x === undefined || x === "") {
    return null;
  }
  if (moment.isMoment(x)) {
    return x.valueOf();
  }
  if (x instanceof Date) {
    return x.getTime();
  }
  if (typeof x === "number") {
    return Number.isFinite(x) ? x : null;
  }
  const m = moment.utc(x, [moment.ISO_8601, "YYYY-MM-DD HH:mm:ss", "YYYY-MM-DD"], true);
  return m.isValid() ? m.valueOf() : null;
}

/**
 * Keep only the last `points` distinct x values, or the last `minutes` before
 * the latest point. Distinct across all series, so two series stay aligned.
 * Returns the data unchanged when the window does not apply -- minutes on an
 * x axis that is not time, say.
 */
export function applyWindow(chartData: any[], window: Partial<ChartWindow> | null | undefined): any[] {
  const w = { ...DEFAULT_WINDOW, ...(window || {}) };
  if (w.mode === "all" || !chartData.length) {
    return chartData;
  }
  const xs: any[] = [];
  const seen = new Set<string>();
  chartData.forEach((s: any) =>
    (s.data || []).forEach((p: any) => {
      const k = String(moment.isMoment(p.x) ? p.x.valueOf() : p.x);
      if (!seen.has(k)) {
        seen.add(k);
        xs.push(p.x);
      }
    })
  );
  const times = xs.map(timeOf);
  const allTimes = times.every((t) => t !== null);

  let keep: Set<string> | null = null;
  if (w.mode === "points") {
    const n = Math.max(1, Math.round(Number(w.points) || DEFAULT_WINDOW.points));
    // Chronological when the x values are times or numbers; otherwise the
    // order they arrived in, which is the query's.
    const ordered = allTimes
      ? xs
          .map((x, i) => ({ x, t: times[i] as number }))
          .sort((a, b) => a.t - b.t)
          .map((o) => o.x)
      : xs;
    keep = new Set(ordered.slice(-n).map((x) => String(moment.isMoment(x) ? x.valueOf() : x)));
  } else if (w.mode === "minutes") {
    if (!allTimes) {
      return chartData;
    }
    const latest = Math.max(...(times as number[]));
    const from = latest - Math.max(0, Number(w.minutes) || DEFAULT_WINDOW.minutes) * 60000;
    keep = new Set(
      xs.filter((_, i) => (times[i] as number) >= from).map((x) => String(moment.isMoment(x) ? x.valueOf() : x))
    );
  }
  if (!keep) {
    return chartData;
  }
  const kept = keep;
  return chartData.map((s: any) => ({
    ...s,
    data: (s.data || []).filter((p: any) => kept.has(String(moment.isMoment(p.x) ? p.x.valueOf() : p.x))),
  }));
}

function lineStyle(line: ReferenceLine) {
  return {
    color: resolveColor(line.color || "critical"),
    type: line.style === "solid" ? "solid" : "dashed",
    width: 1.5,
  };
}

function lineLabel(line: ReferenceLine, fallback: string) {
  return {
    show: true,
    position: "insideEndTop",
    color: resolveColor(line.color || "critical"),
    fontSize: 11,
    formatter: line.label || fallback,
  };
}

const STAT_NAMES: Record<string, string> = { average: "Average", min: "Minimum", max: "Maximum" };

/**
 * Add reference lines and bands to a built cartesian option. Constant lines
 * and bands ride on an empty series of their own, so they do not depend on
 * any data series; statistics are ECharts' own markLine types on the series
 * they describe.
 */
export function addReferences(option: any, options: any, horizontal: boolean): void {
  const lines: ReferenceLine[] = Array.isArray(options.referenceLines) ? options.referenceLines : [];
  const bands: ReferenceBand[] = Array.isArray(options.referenceBands) ? options.referenceBands : [];
  if (!lines.length && !bands.length) {
    return;
  }
  const valueKey = horizontal ? "xAxis" : "yAxis";
  const positionKey = horizontal ? "yAxis" : "xAxis";

  const constantLines: any[] = [];
  lines.forEach((line) => {
    if (line.kind === "average" || line.kind === "min" || line.kind === "max") {
      const target =
        option.series.find((s: any) => line.series && s.name === line.series) ||
        option.series.find((s: any) => s.id !== REFERENCE_SERIES_ID);
      if (!target) {
        return;
      }
      target.markLine = target.markLine || { symbol: "none", silent: true, data: [] };
      target.markLine.data.push({
        type: line.kind,
        lineStyle: lineStyle(line),
        label: lineLabel(line, `${STAT_NAMES[line.kind]} {c}`),
      });
    } else if (line.kind === "x") {
      if (line.value !== null && line.value !== "") {
        constantLines.push({
          [positionKey]: line.value,
          lineStyle: lineStyle(line),
          label: lineLabel(line, String(line.value)),
        });
      }
    } else {
      const v = toNumber(line.value);
      if (v !== null) {
        constantLines.push({ [valueKey]: v, lineStyle: lineStyle(line), label: lineLabel(line, String(v)) });
      }
    }
  });

  const areas = bands
    .filter((b) => toNumber(b.from) !== null || toNumber(b.to) !== null)
    .map((b) => {
      const from = toNumber(b.from);
      const to = toNumber(b.to);
      return [
        {
          [valueKey]: from === null ? "min" : from,
          name: b.label || "",
          // Canvas cannot read CSS color-mix, so the tint is the colour itself
          // at low opacity rather than a wash.
          itemStyle: { color: resolveColor(b.color || "warning"), opacity: 0.12 },
          label: { color: resolveColor(b.color || "warning"), fontSize: 11, position: "insideTopLeft" },
        },
        { [valueKey]: to === null ? "max" : to },
      ];
    });

  if (constantLines.length || areas.length) {
    // The legend lists data series only; an unnamed extra series would
    // otherwise show as an empty entry.
    option.legend = { ...(option.legend || {}), data: option.series.map((s: any) => s.name).filter(Boolean) };
    option.series.push({
      id: REFERENCE_SERIES_ID,
      type: "line",
      data: [],
      silent: true,
      tooltip: { show: false },
      ...(horizontal ? { xAxisIndex: 0, yAxisIndex: 0 } : { yAxisIndex: 0 }),
      markLine: constantLines.length ? { symbol: "none", silent: true, data: constantLines } : undefined,
      markArea: areas.length ? { silent: true, data: areas } : undefined,
    });
  }
}

/** dataZoom components on the category (or time) axis. */
export function zoomComponents(zoom: ZoomMode | undefined, horizontal: boolean): any[] | null {
  if (!zoom || zoom === "none") {
    return null;
  }
  const axis = horizontal ? { yAxisIndex: 0 } : { xAxisIndex: 0 };
  const result: any[] = [];
  if (zoom === "inside" || zoom === "both") {
    result.push({ type: "inside", ...axis, filterMode: "none" });
  }
  if (zoom === "slider" || zoom === "both") {
    result.push({
      type: "slider",
      ...axis,
      filterMode: "none",
      height: horizontal ? undefined : 18,
      width: horizontal ? 18 : undefined,
      brushSelect: false,
    });
  }
  return result;
}
