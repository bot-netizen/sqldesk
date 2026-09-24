import { MONO, SANS, formatValue, resolveColor, thresholdBands } from "@/visualizations/shared/valueOptions";
import { ENTER_DURATION, ENTER_EASING, UPDATE_DURATION, UPDATE_EASING } from "../shared/motion";
import { GaugeOptions } from "./getOptions";

/*
  The reading tile: a gauge that is mostly the number.

  A dial spends a whole widget saying one thing and says nothing about how it
  got there. This style gives the same widget the value large and coloured by
  its threshold, the trail it took to get there, and a bullet bar carrying the
  range, the bands and the target -- which is what a dial's arc was for, in a
  sixth of the space.

  Built from parts that already existed: the stat's sparkline and the progress
  visualization's bullet mode. The number is drawn by a bare `gauge` series
  with everything but its text hidden, the same trick this family already uses
  for the half arc's end labels and the target marker, because a gauge's
  `detail` is the only thing in ECharts that counts a number up to its new
  value.
*/

interface ReadingInput {
  options: GaugeOptions;
  size: { width: number; height: number };
  label: string;
  value: number;
  min: number;
  max: number;
  target: number | null;
  valueColor: string;
  /** Every reading in order, oldest first. One point means no trail. */
  trail: number[];
  colors: { ink: string; muted: string; track: string; rule: string };
}

function clamp(v: number, lo: number, hi: number) {
  return Math.max(lo, Math.min(hi, v));
}

/** Below this the trail is a smear rather than a shape, so it is left out. */
const MIN_TRAIL_HEIGHT = 20;

/**
 * And above this it stops being a trail.
 *
 * Given the whole of a tall widget it became an area chart with a caption,
 * which is a different visualization -- the number is the thing here.
 */
const MAX_TRAIL_HEIGHT = 96;

/** Ticks drop the prefix and suffix: the number above them carries those. */
function endFormat(options: GaugeOptions, min: number, max: number) {
  const big = Math.max(Math.abs(min), Math.abs(max)) >= 10000;
  return {
    ...options.valueFormat,
    prefix: "",
    suffix: "",
    decimals: max - min >= 10 ? 0 : options.valueFormat.decimals,
    style: big ? "compact" : options.valueFormat.style,
  } as any;
}

export default function buildReading(input: ReadingInput): { option: any; signature: string } {
  const { options, size, label, value, min, max, target, valueColor, trail, colors } = input;
  const { ink, muted, track, rule } = colors;

  const side = Math.max(80, Math.min(size.width, size.height * 1.6));
  const pad = clamp(Math.round(side * 0.05), 10, 22);
  const labelSize = clamp(Math.round(side * 0.055), 10, 20);
  const tickSize = clamp(Math.round(side * 0.042), 9, 14);
  // Bigger than the dial styles': there is no arc competing with it.
  const valueSize = clamp(Math.round(side * 0.16), 18, 72);
  const valueHeight = Math.round(valueSize * 1.15);
  const bulletHeight = clamp(Math.round(side * 0.05), 8, 18);

  // The bullet and its end labels are anchored to the bottom; the trail sits
  // just above them; the number takes the middle of whatever is left. Laid
  // out that way round because the trail is the part that must not grow --
  // everything else has a size of its own.
  const endLabelTop = size.height - pad - tickSize;
  const bulletBottom = endLabelTop - 6;
  const bulletTop = bulletBottom - bulletHeight;

  const blockHeight = labelSize + 4 + valueHeight;
  const headroom = bulletTop - 10 - pad;
  const trailHeight = Math.min(Math.round(size.height * 0.3), MAX_TRAIL_HEIGHT, headroom - blockHeight - 8);
  const showTrail = trail.length > 1 && trailHeight >= MIN_TRAIL_HEIGHT;

  const trailBottom = bulletTop - 10;
  const trailTop = trailBottom - trailHeight;
  const blockBottom = showTrail ? trailTop - 8 : trailBottom;
  const labelTop = pad + Math.max(0, (blockBottom - pad - blockHeight) / 2);
  const valueTop = labelTop + labelSize + 4;
  const valueMiddle = valueTop + valueHeight / 2;

  const span = max - min;
  const shown = clamp(value, min, max);
  const ticks = endFormat(options, min, max);

  const series: any[] = [
    {
      // The label and the number. Nothing else of this gauge is drawn.
      type: "gauge",
      min,
      max,
      radius: 1,
      center: ["50%", valueMiddle],
      startAngle: 180,
      endAngle: 0,
      splitNumber: 1,
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { show: false },
      axisLabel: { show: false },
      pointer: { show: false },
      anchor: { show: false },
      progress: { show: false },
      animationDuration: ENTER_DURATION,
      animationEasing: ENTER_EASING,
      animationDurationUpdate: UPDATE_DURATION,
      animationEasingUpdate: UPDATE_EASING,
      title: {
        show: true,
        color: muted,
        fontFamily: SANS,
        fontSize: labelSize,
        offsetCenter: [0, -(valueHeight / 2 + labelSize * 0.6)],
      },
      detail: {
        valueAnimation: true,
        color: valueColor,
        fontFamily: MONO,
        fontWeight: 600,
        fontSize: valueSize,
        offsetCenter: [0, 0],
        // The bullet is clamped to the range; the number is not -- a reading
        // past the maximum should say so. In between ECharts hands the
        // formatter each tweened value, which is what makes it count.
        formatter: (v: number) => formatValue(Math.abs(v - shown) < 1e-9 ? value : v, options.valueFormat),
      },
      data: [{ value: shown, name: label }],
    },
  ];

  if (showTrail) {
    series.push({
      type: "line",
      xAxisIndex: 0,
      yAxisIndex: 0,
      data: trail,
      smooth: true,
      symbol: "none",
      silent: true,
      lineStyle: { color: valueColor, width: 2 },
      areaStyle: { color: valueColor, opacity: 0.14 },
      animationDuration: ENTER_DURATION,
      animationEasing: ENTER_EASING,
      animationDurationUpdate: UPDATE_DURATION,
      animationEasingUpdate: UPDATE_EASING,
    });
  }

  // The bullet's graded bands, in the threshold colours at a wash so the bar
  // in front of them stays the thing being read.
  const bands = thresholdBands(options.thresholds, min, max);
  let cursor = 0;
  bands.forEach((band) => {
    const width = (band.to - cursor) * span;
    cursor = band.to;
    series.push({
      type: "bar",
      xAxisIndex: 1,
      yAxisIndex: 1,
      stack: "bands",
      silent: true,
      barWidth: bulletHeight,
      itemStyle: { color: resolveColor(band.color), opacity: 0.22 },
      data: [width],
      animation: false,
    });
  });

  series.push({
    type: "bar",
    xAxisIndex: 1,
    yAxisIndex: 1,
    silent: true,
    z: 3,
    barWidth: Math.max(4, Math.round(bulletHeight * 0.45)),
    barGap: "-100%",
    itemStyle: { color: valueColor, borderRadius: 1 },
    data: [shown - min],
    animationDuration: ENTER_DURATION,
    animationEasing: ENTER_EASING,
    animationDurationUpdate: UPDATE_DURATION,
    animationEasingUpdate: UPDATE_EASING,
  });

  if (target !== null && Number.isFinite(target)) {
    series.push({
      type: "scatter",
      xAxisIndex: 1,
      yAxisIndex: 1,
      silent: true,
      z: 4,
      symbol: "rect",
      symbolSize: [3, bulletHeight + 6],
      itemStyle: { color: ink },
      data: [[clamp(target, min, max) - min, 0]],
      animation: false,
    });
  }

  const graphic: any[] = [
    {
      type: "text",
      left: pad,
      top: endLabelTop,
      silent: true,
      style: { text: formatValue(min, ticks), fill: muted, font: `${tickSize}px ${MONO}` },
    },
    {
      type: "text",
      right: pad,
      top: endLabelTop,
      silent: true,
      style: { text: formatValue(max, ticks), fill: muted, font: `${tickSize}px ${MONO}`, align: "right" },
    },
  ];

  if (target !== null && Number.isFinite(target)) {
    // Under its own tick -- unless the ends are already there. Three numbers
    // on one line of a narrow widget is two of them unreadable, and the ends
    // are the ones that give the middle its meaning.
    const text = formatValue(target, ticks);
    const at = span > 0 ? (clamp(target, min, max) - min) / span : 0;
    const centre = pad + at * (size.width - pad * 2);
    const halfWidth = (text.length * tickSize * 0.62) / 2;
    const clearOfStart = centre - halfWidth > pad + formatValue(min, ticks).length * tickSize * 0.62 + 8;
    const clearOfEnd = centre + halfWidth < size.width - pad - formatValue(max, ticks).length * tickSize * 0.62 - 8;
    if (clearOfStart && clearOfEnd) {
      graphic.push({
        type: "text",
        left: centre,
        top: endLabelTop,
        silent: true,
        style: { text, fill: ink, font: `${tickSize}px ${MONO}`, align: "center" },
      });
    }
  }

  const option = {
    aria: {
      enabled: true,
      label: {
        description:
          `${label}: ${formatValue(value, options.valueFormat)}, on a scale from ` +
          `${formatValue(min, options.valueFormat)} to ${formatValue(max, options.valueFormat)}` +
          `${target !== null ? `, target ${formatValue(target, options.valueFormat)}` : ""}` +
          `${showTrail ? `, over ${trail.length} readings` : ""}.`,
      },
    },
    grid: [
      // The trail. Off the canvas when there is no room for it, rather than
      // absent: an option with fewer grids than the last one cannot merge.
      showTrail
        ? { left: pad, right: pad, top: trailTop, height: trailHeight }
        : { left: pad, right: pad, top: -1000, height: 1 },
      { left: pad, right: pad, top: bulletTop, height: bulletHeight },
    ],
    xAxis: [
      { type: "category", gridIndex: 0, show: false, boundaryGap: false, data: trail.map((_, i) => i) },
      { type: "value", gridIndex: 1, show: false, min: 0, max: span },
    ],
    yAxis: [
      { type: "value", gridIndex: 0, show: false, scale: true },
      { type: "category", gridIndex: 1, show: false, data: [""] },
    ],
    graphic,
    series,
  };

  // Everything but the moving numbers: how many bands, how many trail points,
  // where the furniture sits. Same shape means the reading can tween.
  const signature = JSON.stringify([
    "reading",
    min,
    max,
    bands.length,
    trail.length,
    showTrail,
    target !== null,
    label,
    options.valueFormat,
    valueSize,
    bulletTop,
  ]);

  return { option, signature };
}
