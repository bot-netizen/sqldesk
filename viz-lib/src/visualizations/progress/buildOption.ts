import {
  formatValue,
  normalizeThresholds,
  thresholdColor,
  resolveColor,
  uiColor,
  toNumber,
} from "../shared/valueOptions";
import { hasColumn, ColumnLike } from "../shared/rows";
import { ProgressOptions } from "./getOptions";

export interface ProgressData {
  columns: ColumnLike[];
  rows: any[];
}

export interface ProgressRow {
  label: string;
  value: number;
  target: number | null;
  /** value / target, or null without a target. */
  ratio: number | null;
  color: string;
}

export interface BuiltProgress {
  option: any;
  signature: string;
  problem: string | null;
  /** Shown under the bars when some rows did not fit. */
  note: string | null;
  rows: ProgressRow[];
}

/** More rows than this and the bars get too thin to read; the rest are dropped with a note. */
export const MAX_BARS = 40;

const SANS = '"Instrument Sans Variable", "Instrument Sans", -apple-system, "Segoe UI", sans-serif';
const MONO = '"JetBrains Mono Variable", "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace';

export function readRows(data: ProgressData, options: ProgressOptions): ProgressRow[] {
  const useTargetColumn = hasColumn(data.columns, options.targetColumn);
  const hasLabels = hasColumn(data.columns, options.labelColumn);
  return (data.rows || [])
    .map((row, i) => {
      const value = toNumber(row && row[options.valueColumn]);
      if (value === null) {
        return null;
      }
      const target = useTargetColumn ? toNumber(row[options.targetColumn]) : options.target;
      const ratio = target !== null && target !== 0 ? value / target : null;
      // Thresholds read percent of target when there is one: "70" means 70%.
      const measured = ratio !== null ? ratio * 100 : value;
      return {
        label: hasLabels ? String(row[options.labelColumn] ?? "") : `Row ${i + 1}`,
        value,
        target,
        ratio,
        color: thresholdColor(measured, options.thresholds) || "neutral",
      };
    })
    .filter((r): r is ProgressRow => r !== null);
}

export default function buildOption(data: ProgressData, options: ProgressOptions): BuiltProgress {
  const empty = { option: {}, signature: "empty", note: null, rows: [] as ProgressRow[] };
  if (!data || !data.rows || !data.rows.length) {
    return { ...empty, problem: "No rows to show." };
  }
  if (!hasColumn(data.columns, options.valueColumn)) {
    return { ...empty, problem: "Choose a value column in the editor." };
  }
  const all = readRows(data, options);
  if (!all.length) {
    return { ...empty, problem: `“${options.valueColumn}” has no numbers.` };
  }
  const rows = all.slice(0, MAX_BARS);

  // With targets, every bar is drawn as percent of its own target, so rows with
  // different goals line up at 100%. Without, the scale is the values'.
  const relative = rows.every((r) => r.ratio !== null);
  const measure = (r: ProgressRow) => (relative ? (r.ratio as number) * 100 : r.value);
  const largest = Math.max(...rows.map(measure));
  const axisMax = relative
    ? Math.max(120, Math.ceil(largest / 10) * 10)
    : options.max !== null && options.max > 0
      ? Math.max(options.max, 0)
      : niceCeil(largest);

  const ink = uiColor("ink");
  const muted = uiColor("muted");
  const track = uiColor("track");
  const rule = uiColor("rule");
  const labels = rows.map((r) => r.label);
  const bullet = options.mode === "bullet";

  const series: any[] = [];

  if (bullet) {
    // Graded bands behind the bar, darker for worse, at the threshold steps.
    const cuts = normalizeThresholds(options.thresholds)
      .steps.map((s) => s.value)
      .filter((v) => v > 0 && v < axisMax);
    const edges = [0, ...cuts, axisMax];
    const shades = [rule, track, "transparent"];
    for (let i = 0; i < edges.length - 1; i += 1) {
      series.push({
        type: "bar",
        stack: "bands",
        silent: true,
        barWidth: "68%",
        itemStyle: { color: i < shades.length - 1 ? shades[i] : track },
        data: rows.map(() => edges[i + 1] - edges[i]),
        animation: false,
      });
    }
  }

  series.push({
    type: "bar",
    name: "value",
    barWidth: bullet ? "26%" : "56%",
    barGap: "-100%",
    z: 3,
    showBackground: !bullet,
    backgroundStyle: { color: track, borderRadius: 4 },
    itemStyle: { borderRadius: bullet ? 1 : 4 },
    data: rows.map((r) => ({ value: Math.min(measure(r), axisMax), itemStyle: { color: resolveColor(r.color) } })),
    animationDurationUpdate: 800,
    animationEasingUpdate: "cubicOut",
  });

  // Values sit in a column of their own at the right edge, not at the end of
  // each bar, where they collided with the target tick and the bands.
  const labelText = rows.map((r) => {
    const pct = r.ratio !== null ? `  ${Math.round(r.ratio * 100)}%` : "";
    return `${formatValue(r.value, options.valueFormat)}${pct}`;
  });
  const labelWidth = Math.min(160, Math.max(...labelText.map((t) => t.length)) * 7 + 16);
  series.push({
    type: "scatter",
    name: "labels",
    silent: true,
    symbolSize: 0,
    data: rows.map((_, i) => [axisMax, i]),
    label: {
      show: true,
      position: "right",
      distance: 12,
      color: ink,
      fontFamily: MONO,
      fontSize: 11,
      formatter: (p: any) => labelText[p.dataIndex],
    },
    animation: false,
  });

  if (relative) {
    series.push({
      type: "scatter",
      name: "target",
      silent: true,
      z: 4,
      symbol: "rect",
      symbolSize: [3, 20],
      itemStyle: { color: ink },
      data: rows.map((_, i) => [100, i]),
      animation: false,
    });
  }

  const longest = Math.max(...labels.map((l) => l.length), 4);
  const option = {
    grid: { left: 12, right: labelWidth, top: 8, bottom: 24, containLabel: true },
    tooltip: {
      trigger: "item",
      formatter: (p: any) => {
        const r = rows[p.dataIndex];
        if (!r) {
          return "";
        }
        const lines = [`<strong>${escapeHtml(r.label)}</strong>`, formatValue(r.value, options.valueFormat)];
        if (r.target !== null) {
          lines.push(`Target ${formatValue(r.target, options.valueFormat)}`);
          if (r.ratio !== null) {
            lines.push(`${Math.round(r.ratio * 100)}% of target`);
          }
        }
        return lines.join("<br>");
      },
    },
    xAxis: {
      type: "value",
      min: 0,
      max: axisMax,
      splitLine: { lineStyle: { color: rule } },
      splitNumber: 4,
      axisLabel: {
        hideOverlap: true,
        color: muted,
        fontFamily: MONO,
        fontSize: 10,
        formatter: (v: number) =>
          relative ? `${v}%` : formatValue(v, { ...options.valueFormat, prefix: "", suffix: "" }),
      },
    },
    yAxis: {
      type: "category",
      data: labels,
      inverse: true,
      axisTick: { show: false },
      axisLine: { show: false },
      axisLabel: {
        color: ink,
        fontFamily: SANS,
        fontSize: 12,
        width: Math.min(160, longest * 8),
        overflow: "truncate",
      },
    },
    aria: {
      enabled: true,
      label: {
        description: rows
          .map(
            (r) =>
              `${r.label}: ${formatValue(r.value, options.valueFormat)}${
                r.ratio !== null ? `, ${Math.round(r.ratio * 100)}% of target` : ""
              }`
          )
          .join("; "),
      },
    },
    series,
  };

  const signature = JSON.stringify([labels, options.mode, relative, axisMax, options.thresholds, options.valueFormat]);
  const note = all.length > MAX_BARS ? `Showing the first ${MAX_BARS} of ${all.length} rows.` : null;
  return { option, signature, problem: null, note, rows };
}

/** 1, 2, 2.5 or 5 times a power of ten, at or above `n`. */
export function niceCeil(n: number): number {
  if (!(n > 0)) {
    return 1;
  }
  const p = Math.pow(10, Math.floor(Math.log10(n)));
  for (const m of [1, 2, 2.5, 5, 10]) {
    if (m * p >= n) {
      return m * p;
    }
  }
  return 10 * p;
}

function escapeHtml(s: string) {
  return s.replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] as string
  );
}
