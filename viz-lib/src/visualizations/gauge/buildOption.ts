import { MONO, SANS } from "@/visualizations/shared/valueOptions";
import { formatValue, thresholdBands, thresholdColor, resolveColor, uiColor, toNumber } from "../shared/valueOptions";
import { pickRow, hasColumn, ColumnLike } from "../shared/rows";
import buildReading from "./reading";
import { GaugeOptions, GaugeStyle } from "./getOptions";
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

/** Clear air between an end label and the arc above it. */
const LABEL_GAP = 5;

/**
 * Where each style puts its arc.
 *
 * One place, because this was declared four times -- the main series, the
 * half style's end-label series, the target marker's angles, and the target
 * marker's radius again as a bare number -- and the four had already drifted:
 * the half style's centre was a constant in one and the literal "72%" in
 * another. Changing a gauge's proportions meant editing all four and getting
 * them to agree.
 *
 * `centreY` and `radiusShare` are fractions so the arithmetic (the target
 * marker needs the radius as a number) and the option (ECharts wants a
 * percentage string) come from the same figure.
 */
type ArcStyle = Exclude<GaugeStyle, "reading">;

const GEOMETRY: Record<ArcStyle, { startAngle: number; endAngle: number; radiusShare: number; centreY: number }> = {
  needle: { startAngle: 215, endAngle: -35, radiusShare: 0.9, centreY: 0.58 },
  half: { startAngle: 180, endAngle: 0, radiusShare: 0.96, centreY: 0.72 },
  ring: { startAngle: 90, endAngle: -270, radiusShare: 0.86, centreY: 0.5 },
};

/** The four ECharts options that place a gauge's arc, from one style. */
function placement(style: ArcStyle) {
  const g = GEOMETRY[style];
  return {
    startAngle: g.startAngle,
    endAngle: g.endAngle,
    radius: `${g.radiusShare * 100}%`,
    center: ["50%", `${g.centreY * 100}%`],
  };
}

function clamp(v: number, lo: number, hi: number) {
  return Math.max(lo, Math.min(hi, v));
}

function timeKey(value: unknown): number {
  if (value === null || value === undefined || value === "") {
    return NaN;
  }
  const n = toNumber(value);
  if (n !== null) {
    return n;
  }
  const t = Date.parse(String(value));
  return Number.isNaN(t) ? NaN : t;
}

/**
 * Rows oldest first by `column`. Rows whose time cannot be read keep their
 * place at the end rather than vanish -- the same rule the stat's sparkline
 * follows, so the two read a time column the same way.
 */
function orderByTime(rows: any[], column: string): any[] {
  return rows
    .map((row, i) => ({ row, i, t: timeKey(row && row[column]) }))
    .sort((a, b) => {
      const at = Number.isNaN(a.t) ? Infinity : a.t;
      const bt = Number.isNaN(b.t) ? Infinity : b.t;
      return at === bt ? a.i - b.i : at - bt;
    })
    .map((x) => x.row);
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
  // The reading style draws a trail, so it may put the rows in the order its
  // time column gives and take the newest as the reading. Every other style
  // sees the rows exactly as the query returned them.
  const trailing = options.style === "reading" && hasColumn(data.columns, options.trailColumn);
  const ordered = trailing ? orderByTime(rows, options.trailColumn) : rows;
  const row = trailing ? ordered[ordered.length - 1] : pickRow(ordered, options.rowNumber);
  const value = toNumber(row && row[options.valueColumn]);
  if (value === null) {
    return {
      ...empty,
      problem: trailing
        ? `“${options.valueColumn}” is not a number in the newest row.`
        : `“${options.valueColumn}” is not a number in that row.`,
    };
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

  // The half style's end labels go *under* the ends of the arc rather than
  // out beside them, which keeps the arc its full size and the labels a few
  // pixels away rather than adrift.
  //
  // A gauge's axis labels sit on the axis and nowhere else: align,
  // verticalAlign and padding are all ignored, so there is no way to drop one
  // below the baseline. What there is, is a second gauge -- the same trick
  // this file already uses for the target marker -- centred a little lower,
  // drawing nothing but those two labels.
  const halfCentreY = GEOMETRY.half.centreY * size.height;
  // Clear of the arc by a few pixels, measured from the text's top edge.
  const endLabelDrop = tickSize / 2 + LABEL_GAP;

  if (options.style === "reading") {
    return {
      ...buildReading({
        options,
        size,
        label,
        value,
        min,
        max,
        target,
        valueColor,
        trail: ordered.map((r) => toNumber(r && r[options.valueColumn])).filter((v): v is number => v !== null),
        colors: { ink, muted, track, rule: uiColor("rule") },
      }),
      problem: null,
    };
  }

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
        ...placement("needle"),
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
        ...placement(half ? "half" : "ring"),
        pointer: { show: false },
        progress: { show: true, overlap: false, roundCap: !half, clip: false, width, itemStyle: { color: valueColor } },
        axisLine: { lineStyle: { width, color: [[1, track]] } },
        // Hidden, but the length and distance still count: ECharts places a
        // label at `radius - splitLine.length - (axisLabel.distance +
        // splitLine.distance)`, and its defaults for those are 10 and 10. Zero
        // them and the label's distance means what it says.
        splitLine: { show: false, length: 0, distance: 0 },
        axisTick: { show: false },
        // Drawn by the second series below, which can sit lower than this one.
        axisLabel: { show: false },
        splitNumber: 1,
        title: { ...common.title, offsetCenter: [0, half ? "22%" : "28%"] },
        detail: { ...common.detail, offsetCenter: [0, half ? "-12%" : "-4%"] },
        data: [{ value: shown, name: label }],
      },
    ];
    if (half) {
      // Nothing but the two end labels, on an axis of the same size sitting a
      // little lower, so they land under the ends of the arc.
      series.push({
        type: "gauge",
        min,
        max,
        ...placement("half"),
        // The same arc, a few pixels lower, so its labels land under the ends
        // of the real one. Pixels rather than a percentage: the drop is a text
        // measurement, not a share of the box.
        center: ["50%", halfCentreY + endLabelDrop],
        silent: true,
        animation: false,
        axisLine: { show: false },
        progress: { show: false },
        pointer: { show: false },
        anchor: { show: false },
        splitLine: { show: false, length: 0, distance: 0 },
        axisTick: { show: false },
        title: { show: false },
        detail: { show: false },
        splitNumber: 1,
        axisLabel: {
          show: true,
          // Half the band, so the label is anchored under the middle of the
          // arc's end rather than its edge.
          distance: width / 2,
          color: muted,
          fontFamily: MONO,
          fontSize: tickSize,
          // Only the two ends.
          formatter: (v: number) => (v === min || v === max ? formatValue(v, tickFormat(options, min, max)) : ""),
        },
        data: [{ value: shown }],
      });
    }
  }

  if (target !== null && Number.isFinite(target)) {
    const arcShare = Math.min(0.4, width / ((side / 2) * GEOMETRY[options.style as ArcStyle].radiusShare));
    // A second, bare gauge whose only visible part is a short pointer sitting
    // on the arc: ECharts has no marker for gauges, and this is how its own
    // examples place one.
    series.push({
      type: "gauge",
      min,
      max,
      ...placement(options.style as ArcStyle),
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
