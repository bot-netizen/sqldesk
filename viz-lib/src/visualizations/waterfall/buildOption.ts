import { formatValue, resolveColor, uiColor } from "../shared/valueOptions";
import { ColumnLike, hasColumn } from "../shared/rows";
import { ECHARTS_MOTION } from "../shared/motion";
import { WaterfallOptions } from "./getOptions";
import buildBars, { barsExtent, WaterfallBar } from "./bars";

export interface WaterfallData {
  columns: ColumnLike[];
  rows: any[];
}

export interface BuiltWaterfall {
  option: any;
  /** Everything but the bar levels: unchanged means tween, changed means redraw. */
  signature: string;
  problem: string | null;
  note: string | null;
}

/** How much of a category band one bar takes. */
const BAR_WIDTH = 0.6;
/** A change of nothing still gets a visible line, or the step looks missing. */
const MIN_BAR_HEIGHT = 1;

/**
 * A waterfall's bars start and end at arbitrary levels, and a fall runs
 * downwards. Stacking an invisible base under a visible bar -- the usual
 * trick -- breaks as soon as the running total crosses zero, because ECharts
 * stacks positive and negative values separately.
 *
 * Drawing the rectangles outright avoids all of that, and the connectors
 * between them come almost free. `renderItem` is how ECharts intends a mark it
 * does not ship to be added; the error bars in chart/echarts use it too.
 */
function renderBar(params: any, api: any) {
  const index = api.value(0);
  const from = api.value(1);
  const to = api.value(2);
  if (!isFinite(from) || !isFinite(to)) {
    return null;
  }

  const start = api.coord([index, from]);
  const end = api.coord([index, to]);
  const width = api.size([1, 0])[0] * BAR_WIDTH;
  const top = Math.min(start[1], end[1]);
  const height = Math.max(Math.abs(end[1] - start[1]), MIN_BAR_HEIGHT);

  return {
    type: "rect",
    // Named so ECharts tweens a bar to its new level instead of redrawing it.
    transition: ["shape"],
    shape: { x: start[0] - width / 2, y: top, width, height, r: 1 },
    style: api.style(),
  };
}

/** The thin steps linking each bar's end to the next bar's start. */
function renderConnector(params: any, api: any) {
  const index = api.value(0);
  const level = api.value(1);
  if (!isFinite(level)) {
    return null;
  }
  const left = api.coord([index, level]);
  const right = api.coord([index + 1, level]);
  const band = api.size([1, 0])[0];
  const half = (band * BAR_WIDTH) / 2;

  return {
    type: "line",
    transition: ["shape"],
    // From the right edge of this bar to the left edge of the next.
    shape: { x1: left[0] + half, y1: left[1], x2: right[0] - half, y2: right[1] },
    style: { stroke: api.visual("color"), lineWidth: 1, lineDash: [3, 3] },
    silent: true,
  };
}

function barColor(bar: WaterfallBar, options: WaterfallOptions): string {
  if (bar.kind === "total") {
    return resolveColor(options.totalColor, "neutral");
  }
  return bar.kind === "fall" ? resolveColor(options.fallColor, "critical") : resolveColor(options.riseColor, "good");
}

export default function buildOption(data: WaterfallData, options: WaterfallOptions): BuiltWaterfall {
  const empty = { option: {}, signature: "empty", note: null };
  const rows = (data && data.rows) || [];
  if (!rows.length) {
    return { ...empty, problem: "No rows to show." };
  }
  if (!hasColumn(data.columns, options.valueColumn)) {
    return { ...empty, problem: "Choose a value column in the editor." };
  }

  const { bars, skipped } = buildBars({
    rows,
    labelColumn: hasColumn(data.columns, options.labelColumn) ? options.labelColumn : "",
    valueColumn: options.valueColumn,
    totalColumn: hasColumn(data.columns, options.totalColumn) ? options.totalColumn : "",
    showTotal: options.showTotal,
    totalLabel: options.totalLabel,
  });
  if (!bars.length) {
    return { ...empty, problem: `“${options.valueColumn}” holds no numbers to add up.` };
  }

  const muted = uiColor("muted");
  const rule = uiColor("rule");
  const extent = barsExtent(bars);
  const format = (v: number) => formatValue(v, options.valueFormat);

  const series: any[] = [];

  if (options.showConnectors && bars.length > 1) {
    // One entry per gap, carrying the level the step is drawn at: the end of
    // this bar, which is also where the next one begins.
    const steps = bars.slice(0, -1).map((bar, i) => ({ value: [i, bars[i + 1].from] }));
    series.push({
      id: "connectors",
      type: "custom",
      renderItem: renderConnector,
      data: steps,
      itemStyle: { color: rule },
      z: 1,
      silent: true,
      animation: false,
      tooltip: { show: false },
    });
  }

  series.push({
    id: "bars",
    type: "custom",
    renderItem: renderBar,
    // x, then the two levels the rectangle spans.
    encode: { x: 0, y: [1, 2] },
    data: bars.map((bar, i) => ({
      value: [i, bar.from, bar.to],
      itemStyle: { color: barColor(bar, options) },
      // A fall's upper edge is where the previous bar ended, which is exactly
      // where the connector runs -- so its label goes underneath instead.
      label: options.showValues ? { position: bar.kind === "fall" ? "bottom" : "top" } : undefined,
    })),
    z: 2,
    label: options.showValues
      ? {
          show: true,
          formatter: (params: any) => format(bars[params.dataIndex].delta),
          color: muted,
          fontSize: 11,
        }
      : { show: false },
  });

  const option = {
    ...ECHARTS_MOTION,
    aria: {
      enabled: true,
      label: {
        description: `A waterfall of ${bars.length} steps in ${options.valueColumn}, ending at ${format(
          bars[bars.length - 1].to
        )}.`,
      },
    },
    grid: { left: 8, right: 16, top: options.showValues ? 24 : 14, bottom: 8, containLabel: true },
    tooltip: {
      trigger: "item",
      confine: true,
      formatter: (params: any) => {
        const bar = bars[params.dataIndex];
        if (!bar) {
          return "";
        }
        if (bar.kind === "total") {
          return `${bar.label}<br/><b>${format(bar.to)}</b>`;
        }
        const sign = bar.delta > 0 ? "+" : "";
        return `${bar.label}<br/><b>${sign}${format(bar.delta)}</b><br/>${format(bar.from)} → ${format(bar.to)}`;
      },
    },
    xAxis: {
      type: "category",
      data: bars.map((b) => b.label),
      axisLabel: { hideOverlap: true, color: muted, interval: 0 },
      axisTick: { alignWithLabel: true },
    },
    yAxis: {
      type: "value",
      // The floor is pinned so the baseline is always on the chart -- a
      // waterfall read against a zero that is off-screen is not read at all.
      // The ceiling is left to ECharts, which rounds outwards and so leaves
      // room above the tallest bar for its label.
      min: extent.min,
      axisLabel: { color: muted, formatter: format, hideOverlap: true },
      splitLine: { lineStyle: { color: rule } },
    },
    series,
  };

  const note =
    skipped > 0 ? `${skipped} row${skipped === 1 ? "" : "s"} had no number in “${options.valueColumn}”.` : null;

  // The steps and their colours are the shape; new levels for the same steps
  // can tween.
  const signature = JSON.stringify([
    bars.map((b) => [b.label, b.kind]),
    options.showValues,
    options.showConnectors,
    options.riseColor,
    options.fallColor,
    options.totalColor,
  ]);

  return { option, signature, problem: null, note };
}
