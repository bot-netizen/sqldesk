import { map } from "lodash";
import escapeHtml from "@/lib/escapeHtml";
import { ECHARTS_MOTION } from "@/visualizations/shared/motion";
import { NO_ROWS } from "@/visualizations/shared/components/Problem";
import { createNumberFormatter } from "@/lib/value-format";
import buildTree, { TreeNode } from "../treemap/tree";
import { TreeOptions } from "./getOptions";

/*
  A hierarchy drawn as a hierarchy.

  The treemap and the sunburst both show one, and both spend their area on
  *size*: a small branch under a large one is a sliver you cannot read the
  name of, and the shape of the hierarchy itself -- how deep it goes, what
  sits beside what, which branch is a chain and which is a fan -- is
  exactly what nesting hides.

  This spends its space on the structure instead. A leaf worth nothing
  takes the same room as a leaf worth millions, which is the point: it
  answers "how is this organised", not "where is the money".

  The hierarchy is built by the treemap's own `buildTree`, so a path that
  groups one way in a treemap groups the same way here. Two builders would
  be two sets of rules about empty levels and duplicate names.
*/

export interface BuiltTreeChart {
  option: any;
  signature: string;
  problem: string | null;
}

export function problemWith(data: any, options: TreeOptions): string | null {
  if (!data || !data.rows || data.rows.length === 0) {
    return NO_ROWS;
  }
  if (!options.pathColumns || !options.pathColumns.length) {
    return "This needs at least one column to build the hierarchy from.";
  }
  if (!options.valueColumn) {
    return "This needs a column for what each leaf is worth.";
  }
  return null;
}

/**
 * ECharts wants one root. A query returns several top-level branches, so
 * they are gathered under a root that is not drawn -- otherwise only the
 * first branch appears, which looks like the data is missing rather than
 * the chart being given more than it asked for.
 */
export const ROOT_NAME = "";

/**
 * What a node is worth, branches included.
 *
 * `buildTree` puts a value on leaves only -- a treemap gets a branch's
 * size from the rectangles inside it and never needs the number. Here the
 * number is the label, so a branch showing nothing beside its name reads
 * as a branch worth nothing rather than one nobody added up.
 */
export function totalOf(node: TreeNode): number {
  if (!node.children || !node.children.length) {
    return node.value || 0;
  }
  return node.children.reduce((sum, child) => sum + totalOf(child), 0);
}

/** Nodes into ECharts' shape, folding anything deeper than asked for. */
export function toEChartsTree(nodes: TreeNode[], initialDepth: number, label: (node: TreeNode) => string): any[] {
  return map(nodes, (node) => ({
    name: label(node),
    value: totalOf(node),
    // Folded rather than hidden: the branch is still there to open, and a
    // tree opened to every level at once is unreadable past about three.
    collapsed: node.depth >= initialDepth && !!(node.children && node.children.length),
    children: node.children ? toEChartsTree(node.children, initialDepth, label) : undefined,
  }));
}

/** About how wide an 11px label is, per character, in the app's sans. */
const LABEL_CHAR_WIDTH = 6.2;

/** The longest label on a leaf showing at the initial depth, in characters. */
export function longestShownLeaf(nodes: TreeNode[], initialDepth: number, label: (node: TreeNode) => string): number {
  let longest = 0;
  const walk = (list: TreeNode[]) =>
    list.forEach((node) => {
      if (!node.children || !node.children.length) {
        longest = Math.max(longest, label(node).length);
      } else if (node.depth < initialDepth) {
        walk(node.children);
      }
      // A branch folded at the initial depth is drawn with its label on the
      // root's side, like any branch, so it needs no room past the leaves.
    });
  walk(nodes);
  return longest;
}

/**
 * The space around the drawing, from what its labels need.
 *
 * ECharts' default is 12% on every side whatever the labels are. Drawn left to
 * right that left a wide empty strip beside the root -- whose name is empty --
 * and squeezed the leaf names against the far edge: 164px of nothing on one
 * side of the demo's tree and its labels crowding the other, found auditing
 * every visualization's margins on the demo dashboard. The leaves' side now
 * gets the width of the longest leaf name, and the root's side a little.
 */
export function treeMargins(layout: string, leafChars: number) {
  const leafRoom = Math.min(260, Math.round(leafChars * LABEL_CHAR_WIDTH) + 24);
  if (layout === "vertical") {
    const side = Math.min(130, Math.round(leafRoom / 2));
    return { top: 28, bottom: 36, left: side, right: side };
  }
  if (layout === "radial") {
    // Labels point outward in every direction; ECharts' even margins suit it.
    return { top: "12%", bottom: "12%", left: "12%", right: "12%" };
  }
  return { top: 16, bottom: 16, left: 24, right: leafRoom };
}

export default function buildOption(data: any, rawOptions: TreeOptions): BuiltTreeChart {
  const problem = problemWith(data, rawOptions);
  if (problem) {
    return { option: { series: [] }, signature: "invalid", problem };
  }

  const built = buildTree(data.rows, rawOptions.pathColumns, rawOptions.valueColumn);
  if (!built.nodes.length) {
    return { option: { series: [] }, signature: "empty", problem: "Nothing in these columns forms a hierarchy." };
  }

  const format = createNumberFormatter(rawOptions.valueFormat);
  const label = (node: TreeNode) => (rawOptions.showValues ? `${node.name}  ${format(totalOf(node))}` : node.name);

  const radial = rawOptions.layout === "radial";
  const vertical = rawOptions.layout === "vertical";

  const option = {
    ...ECHARTS_MOTION,
    tooltip: {
      trigger: "item",
      confine: true,
      formatter: (params: any) => {
        const value = params.data && params.data.value;
        const name = escapeHtml(String(params.name || ""));
        return value === undefined || value === null ? name : `${name}: ${escapeHtml(format(value))}`;
      },
    },
    series: [
      {
        id: "tree",
        type: "tree",
        data: [{ name: ROOT_NAME, children: toEChartsTree(built.nodes, rawOptions.initialDepth, label) }],
        layout: radial ? "radial" : "orthogonal",
        orient: vertical ? "TB" : "LR",
        ...treeMargins(rawOptions.layout, longestShownLeaf(built.nodes, rawOptions.initialDepth, label)),
        roam: true,
        symbolSize: 8,
        initialTreeDepth: rawOptions.initialDepth,
        label: radial
          ? { position: "right", align: "left", fontSize: 11 }
          : vertical
            ? { position: "top", rotate: 0, align: "center", fontSize: 11 }
            : { position: "left", align: "right", fontSize: 11 },
        leaves: {
          label: radial
            ? { position: "right", align: "left" }
            : vertical
              ? { position: "bottom", align: "center" }
              : { position: "right", align: "left" },
        },
        // Hovering a node lifts the whole branch it belongs to, which is
        // how you follow one path out of a crowded tree.
        emphasis: { focus: "descendant" },
        expandAndCollapse: true,
        animationDuration: 400,
        animationDurationUpdate: 500,
      },
    ],
  };

  return {
    option,
    signature: JSON.stringify([
      rawOptions.layout,
      rawOptions.initialDepth,
      rawOptions.showValues,
      built.nodes.length,
      longestShownLeaf(built.nodes, rawOptions.initialDepth, label),
    ]),
    problem: null,
  };
}
