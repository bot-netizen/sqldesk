import { formatValue, uiColor } from "../shared/valueOptions";
import { AllColorPaletteArrays, resolveColorScheme, DEFAULT_COLOR_SCHEME } from "../ColorPalette";
import { ColumnLike, hasColumn } from "../shared/rows";
import { ECHARTS_MOTION } from "../shared/motion";
import { TreemapOptions } from "./getOptions";
import buildTree, { TreeNode, treeDepth } from "./tree";

export interface TreemapData {
  columns: ColumnLike[];
  rows: any[];
}

export interface BuiltTreemap {
  option: any;
  signature: string;
  problem: string | null;
  note: string | null;
}

function toSeriesData(nodes: TreeNode[]): any[] {
  return nodes.map((node) => ({
    name: node.name,
    // A branch's size is the sum of its children, which ECharts works out
    // itself when no value is given.
    ...(node.children && node.children.length ? {} : { value: node.value || 0 }),
    ...(node.children && node.children.length ? { children: toSeriesData(node.children) } : {}),
  }));
}

export default function buildOption(data: TreemapData, options: TreemapOptions): BuiltTreemap {
  const empty = { option: {}, signature: "empty", note: null };
  const rows = (data && data.rows) || [];
  if (!rows.length) {
    return { ...empty, problem: "No rows to show." };
  }

  const pathColumns = options.pathColumns.filter((name) => hasColumn(data.columns, name));
  if (!pathColumns.length) {
    return { ...empty, problem: "Choose at least one grouping column in the editor." };
  }
  if (!hasColumn(data.columns, options.valueColumn)) {
    return { ...empty, problem: "Choose a size column in the editor." };
  }

  const { nodes, total, skipped, unplaced } = buildTree(rows, pathColumns, options.valueColumn);
  if (!nodes.length) {
    return { ...empty, problem: `“${options.valueColumn}” holds no positive numbers to size rectangles by.` };
  }

  const palette = (AllColorPaletteArrays as any)[resolveColorScheme(DEFAULT_COLOR_SCHEME)];
  const muted = uiColor("muted");
  const surface = uiColor("surface");
  const depth = treeDepth(nodes);
  const format = (v: number) => formatValue(v, options.valueFormat);

  const option = {
    ...ECHARTS_MOTION,
    aria: {
      enabled: true,
      label: {
        description: `A treemap of ${options.valueColumn} by ${pathColumns.join(" then ")}, ${format(
          total
        )} across ${nodes.length} top-level groups.`,
      },
    },
    tooltip: {
      trigger: "item",
      confine: true,
      formatter: (params: any) => {
        const path = (params.treePathInfo || [])
          .map((step: any) => step.name)
          .filter(Boolean)
          .join(" → ");
        const share = total > 0 ? (params.value / total) * 100 : 0;
        return `${path || params.name}<br/><b>${format(params.value)}</b> (${share.toFixed(1)}%)`;
      },
    },
    series: [
      {
        id: "treemap",
        type: "treemap",
        data: toSeriesData(nodes),
        // Only this many levels at once; clicking a rectangle opens the next.
        leafDepth: Math.min(options.visibleDepth, Math.max(1, depth)),
        roam: false,
        nodeClick: depth > options.visibleDepth ? "zoomToNode" : false,
        breadcrumb: options.showBreadcrumb
          ? { show: true, bottom: 0, height: 22, itemStyle: { color: surface, textStyle: { color: muted } } }
          : { show: false },
        color: palette,
        label: {
          show: true,
          formatter: options.showValues
            ? (params: any) => `${params.name}\n${format(params.value)}`
            : (params: any) => params.name,
          overflow: "truncate",
          color: "#fff",
          fontSize: 12,
        },
        // The header strip a group carries above the children drawn inside
        // it, so the regions can be told apart and not just the plans.
        upperLabel: { show: depth > 1, height: 18, color: "#fff", fontSize: 11 },
        // A rectangle too small for its name is left blank rather than
        // carrying a name clipped down to one letter.
        labelLayout: { hideOverlap: true },
        itemStyle: { borderColor: surface, borderWidth: 1, gapWidth: 1 },
        levels: [
          { itemStyle: { borderWidth: 0, gapWidth: 3 } },
          { itemStyle: { gapWidth: 1 }, colorSaturation: [0.35, 0.6] },
          { itemStyle: { gapWidth: 1 }, colorSaturation: [0.3, 0.5] },
          { itemStyle: { gapWidth: 1 }, colorSaturation: [0.25, 0.45] },
        ].slice(0, Math.max(1, depth)),
        squareRatio: 0.5 * (1 + Math.sqrt(5)),
        width: "100%",
        height: options.showBreadcrumb ? "92%" : "100%",
        top: 0,
      },
    ],
  };

  const left: string[] = [];
  if (skipped > 0) {
    left.push(`${skipped} row${skipped === 1 ? "" : "s"} had no positive number in “${options.valueColumn}”`);
  }
  if (unplaced > 0) {
    left.push(`${unplaced} had nothing to group by`);
  }
  const note = left.length ? `${left.join(", ")}.` : null;

  // The tree's shape is the shape; new sizes for the same rectangles can tween.
  const signature = JSON.stringify([
    pathColumns,
    options.visibleDepth,
    options.showValues,
    options.showBreadcrumb,
    nodes.map(function names(node: TreeNode): any {
      return [node.name, (node.children || []).map(names)];
    }),
  ]);

  return { option, signature, problem: null, note };
}
