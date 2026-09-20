import { formatValue, resolveColor, uiColor } from "../shared/valueOptions";
import { ColumnLike, hasColumn } from "../shared/rows";
import { ECHARTS_MOTION } from "../shared/motion";
import { HistogramOptions } from "./getOptions";
import binValues, { Bin, readValues } from "./binning";

export interface HistogramData {
  columns: ColumnLike[];
  rows: any[];
}

export interface BuiltHistogram {
  option: any;
  /** Everything but the bar heights: unchanged means tween, changed means redraw. */
  signature: string;
  /** Set when there is nothing sensible to draw; shown instead of the chart. */
  problem: string | null;
  /** Said under the chart when it is worth saying, e.g. rows left out. */
  note: string | null;
}

const MONO = '"JetBrains Mono Variable", "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace';

/**
 * Bin edges sometimes want more decimals than the values themselves: bins
 * 0.1 apart all read "0" at zero decimals, and a row of identical labels says
 * nothing at all.
 *
 * Just enough and no more -- one decimal place per power of ten the bins are
 * narrower than one. Bins 5 apart stay "0" and "5" rather than becoming
 * "0.0" and "5.0".
 */
function edgeFormat(options: HistogramOptions, bins: Bin[]) {
  const span = bins.length ? bins[bins.length - 1].to - bins[0].from : 0;
  const width = bins.length ? span / bins.length : 0;
  // `null` decimals means "let the style decide", which for bin edges is not
  // enough to go on -- the edges have to be told apart from each other.
  let decimals = options.valueFormat.decimals;
  if (width > 0) {
    const needed = Math.min(6, Math.max(0, Math.ceil(-Math.log10(width))));
    decimals = decimals === null ? needed : Math.max(decimals, needed);
  }
  return { ...options.valueFormat, decimals, style: span >= 10000 ? "compact" : options.valueFormat.style } as any;
}

export default function buildOption(data: HistogramData, options: HistogramOptions): BuiltHistogram {
  const empty = { option: {}, signature: "empty", note: null };
  const rows = (data && data.rows) || [];
  if (!rows.length) {
    return { ...empty, problem: "No rows to show." };
  }
  if (!hasColumn(data.columns, options.valueColumn)) {
    return { ...empty, problem: "Choose a column to bin in the editor." };
  }

  const { values, skipped } = readValues(rows, options.valueColumn);
  if (!values.length) {
    return { ...empty, problem: `“${options.valueColumn}” holds no numbers to bin.` };
  }

  const { bins, total } = binValues(values, options.binCount, skipped);
  const format = edgeFormat(options, bins);
  const asPercent = options.countMode === "percent";

  const ink = uiColor("ink");
  const muted = uiColor("muted");
  const barColor = resolveColor(options.color, "accent");

  const edge = (v: number) => formatValue(v, format);
  // The axis carries the lower edge of each bin, so the labels read as a
  // scale rather than as a list of ranges; the full range is in the tooltip.
  const categories = bins.map((b) => edge(b.from));
  const heights = bins.map((b) => (asPercent ? (b.count / total) * 100 : b.count));

  const mean = values.reduce((sum, v) => sum + v, 0) / values.length;

  const series: any[] = [
    {
      id: "bins",
      type: "bar",
      data: heights,
      itemStyle: { color: barColor },
      // What makes it a histogram rather than a bar chart: the bars touch, so
      // the eye reads one continuous distribution.
      barCategoryGap: "0%",
      barGap: "0%",
      emphasis: { itemStyle: { color: barColor, opacity: 0.85 } },
    },
  ];

  if (options.showMean && bins.length > 1) {
    const span = bins[bins.length - 1].to - bins[0].from;
    // A category axis has no room between categories, so the mean is placed by
    // where it falls across the whole range rather than by value.
    const position = span > 0 ? ((mean - bins[0].from) / span) * (bins.length - 1) : 0;
    series[0].markLine = {
      silent: true,
      symbol: "none",
      label: {
        formatter: `mean ${formatValue(mean, options.valueFormat)}`,
        position: "insideEndTop",
        color: ink,
        fontFamily: MONO,
        fontSize: 11,
      },
      lineStyle: { color: ink, type: "dashed", width: 1 },
      data: [{ xAxis: position }],
    };
  }

  const option = {
    ...ECHARTS_MOTION,
    aria: {
      enabled: true,
      label: {
        description: `A histogram of ${options.valueColumn}: ${total} values in ${bins.length} bins, from ${edge(
          bins[0].from
        )} to ${edge(bins[bins.length - 1].to)}.`,
      },
    },
    grid: { left: 8, right: 16, top: 14, bottom: 8, containLabel: true },
    tooltip: {
      trigger: "axis",
      confine: true,
      axisPointer: { type: "shadow" },
      formatter: (params: any) => {
        const first = Array.isArray(params) ? params[0] : params;
        const bin = bins[first.dataIndex];
        if (!bin) {
          return "";
        }
        const share = total > 0 ? (bin.count / total) * 100 : 0;
        // Bracket notation rather than a dash, because which end a bin owns is
        // exactly the thing a reader checking a boundary value wants to know:
        // every bin stops short of its upper edge except the last, which
        // includes it.
        const closing = first.dataIndex === bins.length - 1 ? "]" : ")";
        const range = bin.from === bin.to ? edge(bin.from) : `[${edge(bin.from)}, ${edge(bin.to)}${closing}`;
        return `${range}<br/><b>${bin.count}</b> of ${total} (${share.toFixed(1)}%)`;
      },
    },
    xAxis: {
      type: "category",
      data: categories,
      name: options.valueColumn,
      nameLocation: "middle",
      nameGap: 30,
      axisLabel: { hideOverlap: true, color: muted },
      axisTick: { alignWithLabel: false },
    },
    yAxis: {
      type: "value",
      name: asPercent ? "share" : "rows",
      nameLocation: "middle",
      nameGap: 40,
      axisLabel: {
        color: muted,
        formatter: (v: number) => (asPercent ? `${v}%` : String(v)),
        hideOverlap: true,
      },
      splitLine: { lineStyle: { color: uiColor("rule") } },
    },
    series,
  };

  const note =
    skipped > 0 ? `${skipped} row${skipped === 1 ? "" : "s"} had no number in “${options.valueColumn}”.` : null;

  // The bins are the shape; the same bins with new counts can tween.
  const signature = JSON.stringify([categories, asPercent, options.color, options.showMean, options.valueColumn]);

  return { option, signature, problem: null, note };
}
