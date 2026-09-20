import { map } from "lodash";
import { AllColorPaletteArrays, DEFAULT_COLOR_SCHEME } from "@/visualizations/ColorPalette";
import { boxStats } from "@/visualizations/chart/echarts/boxplot";
import { cleanNumber } from "@/visualizations/chart/echarts/utils";
import { ECHARTS_MOTION } from "@/visualizations/shared/motion";

// This visualization draws one box per numeric column, which is what makes it
// different from the Chart visualization's box type: there, the boxes come from
// grouping rows by a category. It is deprecated, so it keeps that behaviour
// exactly -- the point of moving it off d3 v3 was to retire the dependency, not
// to change anyone's chart.

export interface BuiltBoxPlot {
  option: any;
  signature: string;
  /** Set when there is nothing to draw a box from. */
  problem: string | null;
}

function palette(): string[] {
  return (AllColorPaletteArrays as any)[DEFAULT_COLOR_SCHEME];
}

const AXIS_NAME_GAP = 30;

function axisTitle(label: any) {
  return label ? { name: label, nameLocation: "middle", nameGap: AXIS_NAME_GAP } : {};
}

/**
 * Room for the axis names.
 *
 * `containLabel` reserves space for axis *labels* but not for an axis *name*,
 * so a rotated y-axis title runs off the left edge of the canvas. The gap plus
 * a line of text is what it needs.
 */
function gridFor(options: any) {
  const room = AXIS_NAME_GAP + 14;
  return {
    left: options.yAxisLabel ? room : 12,
    right: 12,
    top: 24,
    bottom: options.xAxisLabel ? room : 24,
    containLabel: true,
  };
}

export default function buildOption(data: any, options: any): BuiltBoxPlot {
  const columns = map(data.columns, (column: any) => column.name);
  const colors = palette();

  // A column with nothing numeric in it is left out entirely rather than
  // holding an empty place in the row of boxes: ECharts' boxplot series reads
  // `.value` off every item it is given and throws outright on a null, which
  // took the whole widget down for any result carrying a text or date column
  // beside its numbers -- which is most of them.
  const drawn: { column: string; box: number[] }[] = [];
  const outliers: any[] = [];

  columns.forEach((column) => {
    const values: number[] = [];
    data.rows.forEach((row: any) => {
      const value = cleanNumber(row[column]);
      if (value !== null) {
        values.push(value);
      }
    });

    const stats = boxStats(values);
    if (!stats) {
      return;
    }
    // Outliers are placed against the boxes actually drawn, not against the
    // columns the result happened to have.
    const index = drawn.length;
    drawn.push({ column, box: [stats.low, stats.q1, stats.median, stats.q3, stats.high] });
    stats.outliers.forEach((value) => outliers.push([index, value]));
  });

  const categories = drawn.map((d) => d.column);
  const boxes = drawn.map((d) => d.box);

  if (!boxes.length) {
    return { option: {}, signature: "empty", problem: "No numeric column to draw a box from." };
  }

  const series: any[] = [
    {
      id: "boxplot",
      name: "Boxplot",
      type: "boxplot",
      data: boxes,
      itemStyle: { color: "transparent", borderColor: colors[0], borderWidth: 1.5 },
      emphasis: { itemStyle: { borderWidth: 2 } },
    },
  ];

  if (outliers.length > 0) {
    series.push({
      id: "boxplot:outliers",
      name: "Outliers",
      type: "scatter",
      data: outliers,
      symbolSize: 4,
      itemStyle: { color: colors[0] },
      legendHoverLink: false,
      z: 3,
    });
  }

  const option = {
    ...ECHARTS_MOTION,
    grid: gridFor(options),
    xAxis: { type: "category", data: categories, ...axisTitle(options.xAxisLabel) },
    yAxis: { type: "value", scale: true, splitArea: { show: true }, ...axisTitle(options.yAxisLabel) },
    tooltip: {
      trigger: "item",
      confine: true,
    },
    series,
  };

  // The columns are the boxes, so a new or renamed column is a different chart
  // rather than new values for the same one.
  return { option, signature: JSON.stringify(categories), problem: null };
}
