import { formatValue, thresholdBands, thresholdColor, resolveColor, uiColor, toNumber } from "../shared/valueOptions";
import { pickRow, hasColumn, ColumnLike } from "../shared/rows";
import { GaugeOptions } from "./getOptions";
import { ENTER_DURATION, ENTER_EASING, UPDATE_DURATION, UPDATE_EASING } from "../shared/motion";

export interface GaugeData {
  columns: ColumnLike[];
  rows: any[];
}

export interface BuiltGauge {
  option: any;
  /** Everything but the moving value: unchanged means tween, changed means redraw. */
  signature: string;
  /** Set when there is nothing sensible to draw; shown instead of the chart. */
  problem: string | null;
}

const MONO = '"JetBrains Mono Variable", "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace';
const SANS = '"Instrument Sans Variable", "Instrument Sans", -apple-system, "Segoe UI", sans-serif';

function clamp(v: number, lo: number, hi: number) {
  return Math.max(lo, Math.min(hi, v));
}

/** Tick labels drop the prefix and suffix and go compact once numbers get long. */
function tickFormat(options: GaugeOptions, min: number, max: number) {
  const big = Math.max(Math.abs(min), Math.abs(max)) >= 10000;
  // The reading keeps its decimals ("62.9%"); ticks on a wide scale fall on
  // whole numbers, and "20.0 40.0 60.0" only crowds the arc.
  const decimals = max - min >= 10 ? 0 : options.valueFormat.decimals;
  return {
    ...options.valueFormat,
    prefix: "",
    suffix: "",
    decimals,
    style: big ? "compact" : options.valueFormat.style,
  } as any;
}

function readRange(data: GaugeData, row: any, options: GaugeOptions) {
  const fromColumn = (column: string, fallback: number) => {
    if (!hasColumn(data.columns, column) || !row) {
      return fallback;
    }
    const n = toNumber(row[column]);
    return n === null ? fallback : n;
  };
  return { min: fromColumn(options.minColumn, options.min), max: fromColumn(options.maxColumn, options.max) };
}

export default function buildOption(
  data: GaugeData,
  options: GaugeOptions,
  size: { width: number; height: number } = { width: 300, height: 220 }
): BuiltGauge {
  const empty = { option: {}, signature: "empty" };
  const rows = (data && data.rows) || [];
  if (!rows.length) {
    return { ...empty, problem: "No rows to show." };
  }
  if (!hasColumn(data.columns, options.valueColumn)) {
    return { ...empty, problem: "Choose a value column in the editor." };
  }
  const row = pickRow(rows, options.rowNumber);
  const value = toNumber(row && row[options.valueColumn]);
  if (value === null) {
    return { ...empty, problem: `“${options.valueColumn}” is not a number in that row.` };
  }
  const { min, max } = readRange(data, row, options);
  if (!(max > min)) {
    return { ...empty, problem: "The maximum must be above the minimum." };
  }
  const target = hasColumn(data.columns, options.targetColumn)
    ? toNumber(row[options.targetColumn])
    : options.target !== null && Number.isFinite(options.target)
      ? options.target
      : null;

  const ink = uiColor("ink");
  const muted = uiColor("muted");
  const track = uiColor("track");
  const surface = uiColor("surface");
  const valueColor = resolveColor(thresholdColor(value, options.thresholds), "accent");
  const bands = thresholdBands(options.thresholds, min, max).map((b) => [b.to, resolveColor(b.color)]);
  const label = options.label || options.valueColumn;

  // Text scales with the widget: a gauge is read from across a room as often
  // as from a desk.
  const side = Math.max(80, Math.min(size.width, size.height * (options.style === "half" ? 1.6 : 1)));
  // 0.11 of the side keeps a unit like " ms" clear of the end tick labels.
  const valueSize = clamp(Math.round(side * 0.11), 14, 48);
  const labelSize = clamp(Math.round(side * 0.05), 10, 18);
  const tickSize = clamp(Math.round(side * 0.04), 9, 13);
  const width = clamp(Math.round(side * 0.06), 6, 22);

  const shown = clamp(value, min, max);
  const common = {
    type: "gauge",
    min,
    max,
    // Sweeps up from the minimum when the dashboard opens, and eases to each
    // new reading after.
    animationDuration: ENTER_DURATION,
    animationEasing: ENTER_EASING,
    animationDurationUpdate: UPDATE_DURATION,
    animationEasingUpdate: UPDATE_EASING,
    title: {
      color: muted,
      fontFamily: SANS,
      fontSize: labelSize,
    },
    detail: {
      valueAnimation: true,
      color: options.style === "needle" ? ink : valueColor,
      fontFamily: MONO,
      fontWeight: 600,
      fontSize: valueSize,
      // The needle is clamped to the dial; the number is not -- a reading past
      // the maximum should say so. In between, ECharts hands the formatter
      // each tweened value, which is what makes the number count.
      formatter: (v: number) => formatValue(Math.abs(v - shown) < 1e-9 ? value : v, options.valueFormat),
    },
  };

  let series: any[];
  if (options.style === "needle") {
    series = [
      {
        ...common,
        startAngle: 215,
        endAngle: -35,
        radius: "90%",
        center: ["50%", "58%"],
        splitNumber: 5,
        axisLine: { lineStyle: { width, color: bands } },
        pointer: { length: "60%", width: Math.max(3, Math.round(width / 3)), itemStyle: { color: ink } },
        anchor: {
          show: true,
          size: Math.max(8, Math.round(width * 0.9)),
          itemStyle: { color: ink, borderColor: surface, borderWidth: 2 },
        },
        axisTick: { distance: -width, length: Math.round(width / 2), lineStyle: { color: surface, width: 1 } },
        splitLine: { distance: -width, length: width, lineStyle: { color: surface, width: 2 } },
        axisLabel: {
          distance: width + 6,
          color: muted,
          fontFamily: MONO,
          fontSize: tickSize,
          formatter: (v: number) => formatValue(v, tickFormat(options, min, max)),
        },
        title: { ...common.title, offsetCenter: [0, "80%"] },
        detail: { ...common.detail, offsetCenter: [0, "52%"] },
        data: [{ value: shown, name: label }],
      },
    ];
  } else {
    const half = options.style === "half";
    series = [
      {
        ...common,
        startAngle: half ? 180 : 90,
        endAngle: half ? 0 : -270,
        radius: half ? "96%" : "86%",
        center: half ? ["50%", "72%"] : ["50%", "50%"],
        pointer: { show: false },
        progress: { show: true, overlap: false, roundCap: !half, clip: false, width, itemStyle: { color: valueColor } },
        axisLine: { lineStyle: { width, color: [[1, track]] } },
        splitLine: { show: false },
        axisTick: { show: false },
        axisLabel: half
          ? {
              show: true,
              distance: -width - 4,
              color: muted,
              fontFamily: MONO,
              fontSize: tickSize,
              // Only the two ends: min under the left, max under the right.
              formatter: (v: number) => (v === min || v === max ? formatValue(v, tickFormat(options, min, max)) : ""),
            }
          : { show: false },
        splitNumber: 1,
        title: { ...common.title, offsetCenter: [0, half ? "22%" : "28%"] },
        detail: { ...common.detail, offsetCenter: [0, half ? "-12%" : "-4%"] },
        data: [{ value: shown, name: label }],
      },
    ];
  }

  if (target !== null && Number.isFinite(target)) {
    const radiusShare = options.style === "needle" ? 0.9 : options.style === "half" ? 0.96 : 0.86;
    const arcShare = Math.min(0.4, width / ((side / 2) * radiusShare));
    const angles =
      options.style === "needle"
        ? { startAngle: 215, endAngle: -35, radius: "90%", center: ["50%", "58%"] }
        : options.style === "half"
          ? { startAngle: 180, endAngle: 0, radius: "96%", center: ["50%", "72%"] }
          : { startAngle: 90, endAngle: -270, radius: "86%", center: ["50%", "50%"] };
    // A second, bare gauge whose only visible part is a short pointer sitting
    // on the arc: ECharts has no marker for gauges, and this is how its own
    // examples place one.
    series.push({
      type: "gauge",
      min,
      max,
      ...angles,
      silent: true,
      z: 5,
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { show: false },
      axisLabel: { show: false },
      progress: { show: false },
      anchor: { show: false },
      title: { show: false },
      detail: { show: false },
      // Offset and length are fractions of the radius: the tick starts a
      // little inside the arc's inner edge and ends a little past its outer
      // one, so it reads as crossing the band.
      pointer: {
        icon: "rect",
        width: 3,
        length: `${Math.round((arcShare + 0.08) * 100)}%`,
        offsetCenter: [0, `-${Math.round((1 - arcShare - 0.04) * 100)}%`],
        itemStyle: { color: ink },
      },
      animationDurationUpdate: UPDATE_DURATION,
      data: [{ value: clamp(target, min, max), name: "target" }],
    });
  }

  const option = {
    aria: {
      enabled: true,
      label: {
        description: `${label}: ${formatValue(value, options.valueFormat)}, on a scale from ${formatValue(
          min,
          options.valueFormat
        )} to ${formatValue(max, options.valueFormat)}${
          target !== null ? `, target ${formatValue(target, options.valueFormat)}` : ""
        }.`,
      },
    },
    series,
  };

  const signature = JSON.stringify([
    options.style,
    min,
    max,
    options.thresholds,
    options.valueFormat,
    label,
    target !== null,
    valueSize,
    width,
  ]);

  return { option, signature, problem: null };
}
