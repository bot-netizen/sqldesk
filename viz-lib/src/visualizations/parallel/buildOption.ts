import { each, map } from "lodash";
import escapeHtml from "@/lib/escapeHtml";
import { ECHARTS_MOTION } from "@/visualizations/shared/motion";
import { NO_ROWS } from "@/visualizations/shared/components/Problem";
import { createNumberFormatter } from "@/lib/value-format";
import { ParallelOptions } from "./getOptions";

/*
  Many measures at once, one line per row.

  A scatter compares two things. A chart with six series compares six
  things against one axis. Neither answers "which of these rows is unlike
  the others, across everything we measured" -- which is the question
  behind most outlier hunting, and the question this shape exists for.

  Each column gets a vertical axis; each row is a line crossing all of
  them. Rows that behave alike run parallel; one that crosses the rest is
  the one worth looking at.
*/

export interface BuiltParallel {
  option: any;
  signature: string;
  problem: string | null;
}

export function problemWith(data: any, options: ParallelOptions): string | null {
  if (!data || !data.rows || data.rows.length === 0) {
    return NO_ROWS;
  }
  // One axis is a strip chart. The whole point is what happens between
  // axes, so there have to be at least two.
  if (!options.dimensionColumns || options.dimensionColumns.length < 2) {
    return "This needs at least two numeric columns: one vertical axis each.";
  }
  return null;
}

/**
 * How see-through to draw the lines.
 *
 * A thousand opaque lines is a solid block with no shape in it. Fading
 * them turns overlap into density, which is what makes a crowd of rows
 * readable -- but faded too far a handful of rows disappears entirely, so
 * it only starts fading once there is a crowd to fade.
 */
export function lineOpacity(rowCount: number): number {
  if (rowCount <= 30) {
    return 0.85;
  }
  if (rowCount <= 200) {
    return 0.45;
  }
  if (rowCount <= 1000) {
    return 0.2;
  }
  return 0.08;
}

function asNumber(value: any): number | null {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

/**
 * Rows into lines.
 *
 * A row missing any dimension is dropped: a line that skips an axis is
 * drawn straight through it, which reads as a value sitting wherever the
 * gap happened to land.
 */
export function linesFrom(
  rows: any[],
  options: ParallelOptions
): { byGroup: Map<string, number[][]>; dropped: number } {
  const byGroup = new Map<string, number[][]>();
  let dropped = 0;

  each(rows, (row) => {
    const line: number[] = [];
    let complete = true;
    each(options.dimensionColumns, (column) => {
      const value = asNumber(row[column]);
      if (value === null) {
        complete = false;
        return false;
      }
      line.push(value);
      return true;
    });
    if (!complete) {
      dropped += 1;
      return;
    }
    const group = options.seriesColumn ? String(row[options.seriesColumn] ?? "") : "";
    const existing = byGroup.get(group);
    if (existing) {
      existing.push(line);
    } else {
      byGroup.set(group, [line]);
    }
  });

  return { byGroup, dropped };
}

export default function buildOption(data: any, rawOptions: ParallelOptions): BuiltParallel {
  const problem = problemWith(data, rawOptions);
  if (problem) {
    return { option: { series: [] }, signature: "invalid", problem };
  }

  const { byGroup } = linesFrom(data.rows, rawOptions);
  const total = Array.from(byGroup.values()).reduce((sum, lines) => sum + lines.length, 0);
  if (!total) {
    return {
      option: { series: [] },
      signature: "empty",
      problem: "No row has a number in every one of those columns.",
    };
  }

  const format = createNumberFormatter(rawOptions.valueFormat);
  const opacity = lineOpacity(total);
  const groups = Array.from(byGroup.keys());
  const grouped = !!rawOptions.seriesColumn;

  const option = {
    ...ECHARTS_MOTION,
    tooltip: { trigger: "item", confine: true },
    legend:
      grouped && rawOptions.showLegend ? { show: true, type: "scroll", bottom: 0, icon: "roundRect" } : { show: false },
    parallel: {
      left: 40,
      right: 40,
      top: 24,
      bottom: grouped && rawOptions.showLegend ? 46 : 24,
      parallelAxisDefault: {
        nameLocation: "start",
        nameGap: 14,
        axisLabel: { formatter: (value: any) => format(value) },
      },
    },
    parallelAxis: map(rawOptions.dimensionColumns, (column, index) => ({
      dim: index,
      name: column,
    })),
    series: map(groups, (group) => ({
      id: `parallel:${group}`,
      name: group || "All rows",
      type: "parallel",
      data: byGroup.get(group),
      lineStyle: { opacity, width: 1 },
      // Hovering one line lifts it clear of the crowd, which on a faded
      // plot is the only way to follow a single row across the axes.
      emphasis: { lineStyle: { width: 2.5, opacity: 1 } },
      tooltip: {
        formatter: (params: any) =>
          map(
            rawOptions.dimensionColumns,
            (column, index) => `${escapeHtml(column)}: ${escapeHtml(format((params.value || [])[index]))}`
          ).join("<br/>"),
      },
    })),
  };

  // The axes and the groups are the shape.
  return {
    option,
    signature: JSON.stringify([rawOptions.dimensionColumns, groups]),
    problem: null,
  };
}
