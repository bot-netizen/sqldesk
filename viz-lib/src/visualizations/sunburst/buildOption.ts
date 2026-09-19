/**
 * Sequence sunburst: each row is a path through a set of stages, and the arcs
 * are how many journeys took each path.
 *
 * The hierarchy building below is the original d3 version's, unchanged -- only
 * the drawing moved.
 */
import { compact, every, filter, find, first, groupBy, has, identity, keys, map, sortBy } from "lodash";
import { ECHARTS_MOTION } from "@/visualizations/shared/motion";

// A path that stops early still consumes its share of the parent's arc, so the
// stop is a real node in the tree. The d3 version filtered these out at draw
// time; here they are drawn transparent, which keeps the proportions identical
// without inventing a visible segment.
const EXIT_NODE = "<<<Exit>>>";

// d3 v3's `scale.category10`, so existing sunbursts keep their colours.
const CATEGORY_10 = [
  "#1f77b4",
  "#ff7f0e",
  "#2ca02c",
  "#d62728",
  "#9467bd",
  "#8c564b",
  "#e377c2",
  "#7f7f7f",
  "#bcbd22",
  "#17becf",
];

function categoryColors() {
  const assigned = new Map<string, string>();
  return (key: string) => {
    if (!assigned.has(key)) {
      assigned.set(key, CATEGORY_10[assigned.size % CATEGORY_10.length]);
    }
    return assigned.get(key) as string;
  };
}

function buildNodesFromHierarchyData(data: any) {
  const grouped = groupBy(data, "sequence");

  return map(grouped, (value) => {
    const sorted = sortBy(value, "stage");
    return {
      size: value[0].value || 0,
      sequence: value[0].sequence,
      nodes: map(sorted, (i) => i.node),
    };
  });
}

function buildNodesFromTableData(data: any) {
  const validKey = (key: any) => key !== "value";
  const dataKeys = sortBy(filter(keys(data[0]), validKey), identity);

  return map(data, (row: any, sequence) => ({
    size: row.value || 0,
    sequence,
    nodes: compact(map(dataKeys, (key) => row[key])),
  }));
}

function isDataInHierarchyFormat(data: any) {
  const firstRow = first(data);
  return every(["sequence", "stage", "node", "value"], (field) => has(firstRow, field));
}

export function buildHierarchy(data: any) {
  data = isDataInHierarchyFormat(data) ? buildNodesFromHierarchyData(data) : buildNodesFromTableData(data);

  const root: any = { name: "root", children: [] as any[] };

  data.forEach((d: any) => {
    const nodes = d.nodes;
    const size = parseInt(d.size, 10);

    let currentNode = root;
    for (let j = 0; j < nodes.length; j += 1) {
      let children = currentNode.children;
      const nodeName = nodes[j];
      const isLeaf = j + 1 === nodes.length;

      if (!children) {
        currentNode.children = children = [];
        children.push({ name: EXIT_NODE, size: currentNode.size });
      }

      let childNode = find(children, (child: any) => child.name === nodeName);

      if (isLeaf && childNode) {
        childNode.children = childNode.children || [];
        childNode.children.push({ name: EXIT_NODE, size });
      } else if (isLeaf) {
        children.push({ name: nodeName, size });
      } else {
        if (!childNode) {
          childNode = { name: nodeName, children: [] };
          children.push(childNode);
        }
        currentNode = childNode;
      }
    }
  });

  return root;
}

/** Convert the tree into the shape ECharts' sunburst series expects. */
function toSeriesData(node: any, color: (key: string) => string, depth = 0): any {
  const isExit = node.name === EXIT_NODE;
  const item: any = {
    name: node.name,
    // ECharts sums children when a value is absent, which is what we want for
    // branches; leaves carry their own count.
    ...(node.children ? {} : { value: node.size || 0 }),
  };

  if (isExit) {
    // Present for the arithmetic, invisible in the drawing -- the d3 version
    // filtered these out of the node list entirely.
    item.itemStyle = { color: "transparent", borderWidth: 0 };
    item.label = { show: false };
    item.emphasis = { disabled: true };
    item.silent = true;
  } else {
    item.itemStyle = { color: color(node.name), borderWidth: 1, borderColor: "#fff" };
  }

  if (node.children) {
    item.children = map(node.children, (child: any) => toSeriesData(child, color, depth + 1));
  }
  return item;
}

export function isDataValid(data: any) {
  return data && data.rows.length > 0;
}

export interface BuiltSunburst {
  option: any;
  signature: string;
}

export default function buildOption(data: any): BuiltSunburst {
  if (!isDataValid(data)) {
    return { option: { series: [] }, signature: "empty" };
  }

  const color = categoryColors();
  const root = buildHierarchy(data.rows);
  const seriesData = map(root.children || [], (child: any) => toSeriesData(child, color, 1));

  const option = {
    ...ECHARTS_MOTION,
    tooltip: {
      trigger: "item",
      confine: true,
      formatter: (params: any) => {
        const path = map(
          filter(params.treePathInfo || [], (step: any) => step.name && step.name !== "root"),
          (step: any) => step.name
        ).join(" → ");
        return `${path}<br/><b>${params.value}</b>`;
      },
    },
    series: [
      {
        id: "sunburst",
        type: "sunburst",
        radius: ["12%", "95%"],
        data: seriesData,
        sort: null,
        label: { show: true, minAngle: 8, rotate: "tangential", color: "#fff" },
        emphasis: { focus: "ancestor" },
      },
    ],
  };

  // The set of paths is the shape; the same paths with new counts can tween.
  return { option, signature: JSON.stringify(seriesData, (key, value) => (key === "value" ? undefined : value)) };
}
