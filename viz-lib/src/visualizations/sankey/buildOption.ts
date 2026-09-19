import { every, filter, find, isFinite, isNaN, isNil, isNumber, isString, keys, map, mapValues, sortBy } from "lodash";
import { ECHARTS_MOTION } from "@/visualizations/shared/motion";

// The data shape is the inherited one: up to five stage columns plus a `value`
// column, one row per path through the stages. That contract is unchanged --
// only the drawing moved off d3 v3.

// d3 v3's `scale.category20`, so existing sankeys keep their colours.
const CATEGORY_20 = [
  "#1f77b4",
  "#aec7e8",
  "#ff7f0e",
  "#ffbb78",
  "#2ca02c",
  "#98df8a",
  "#d62728",
  "#ff9896",
  "#9467bd",
  "#c5b0d5",
  "#8c564b",
  "#c49c94",
  "#e377c2",
  "#f7b6d2",
  "#7f7f7f",
  "#c7c7c7",
  "#bcbd22",
  "#dbdb8d",
  "#17becf",
  "#9edae5",
];

/** d3 v3 assigned a palette colour per distinct key, in first-seen order. */
function categoryColors() {
  const assigned = new Map<string, string>();
  return (key: string) => {
    if (!assigned.has(key)) {
      assigned.set(key, CATEGORY_20[assigned.size % CATEGORY_20.length]);
    }
    return assigned.get(key) as string;
  };
}

export interface SankeyNode {
  /** Unique across the graph: the same label at two stages is two nodes. */
  name: string;
  displayName: string;
  depth: number;
  itemStyle: { color: string };
}

export interface SankeyLink {
  source: string;
  target: string;
  value: number;
}

function normalizeName(name: any) {
  return isNil(name) ? "Exit" : `${name}`;
}

/**
 * Turn the stage columns into nodes and links.
 *
 * A label can repeat at different stages and mean something different each
 * time, so a node's identity is its label *and* its depth. ECharts addresses
 * links by node name, so that pair has to be folded into the name itself and
 * the label shown separately.
 */
export function buildGraph(rows: any[]): { nodes: SankeyNode[]; links: SankeyLink[] } {
  const nodesByKey = new Map<string, SankeyNode>();
  const linksByKey = new Map<string, SankeyLink>();
  const color = categoryColors();

  const dataKeys = sortBy(
    filter(keys(rows[0] || {}), (key) => key !== "value"),
    (key) => key
  );

  function nodeFor(label: any, depth: number) {
    const displayName = normalizeName(label);
    const name = `${displayName}${depth}`;
    let node = nodesByKey.get(name);
    if (!node) {
      node = {
        name,
        displayName,
        depth: depth - 1,
        // d3 coloured by the first word of the label, so "Signup A" and
        // "Signup B" shared a colour. Kept.
        itemStyle: { color: color(displayName.replace(/ .*/, "")) },
      };
      nodesByKey.set(name, node);
    }
    return node;
  }

  function addLink(sourceLabel: any, targetLabel: any, value: any, depth: number) {
    // A blank stage beyond the first means the path stopped earlier; joining it
    // onward would invent a journey nobody took.
    if ((sourceLabel === "" || !sourceLabel) && depth > 1) {
      return;
    }
    const source = nodeFor(sourceLabel, depth);
    const target = nodeFor(targetLabel, depth + 1);
    const key = `${source.name}${target.name}`;
    const existing = linksByKey.get(key);
    const amount = parseInt(value, 10) || 0;
    if (existing) {
      existing.value += amount;
    } else {
      linksByKey.set(key, { source: source.name, target: target.name, value: amount });
    }
  }

  rows.forEach((row: any) => {
    for (let depth = 1; depth <= 4; depth += 1) {
      addLink(row[dataKeys[depth - 1]], row[dataKeys[depth]], row.value || 0, depth);
    }
    // Ensures the last stage has a corresponding exit node.
    addLink(row[dataKeys[4]], null, row.value || 0, 5);
  });

  return {
    nodes: Array.from(nodesByKey.values()),
    // A zero-weight link draws nothing and confuses the layout.
    links: filter(Array.from(linksByKey.values()), (link) => link.value > 0),
  };
}

/** Coerce numeric strings, the way the d3 version did before validating. */
export function prepareDataRows(rows: any[]) {
  return map(rows, (row) =>
    mapValues(row, (v: any) => {
      if (!v || isNumber(v)) {
        return v;
      }
      return isNaN(parseFloat(v)) ? v : parseFloat(v);
    })
  );
}

export function isDataValid(data: any): boolean {
  // Without a `value` column there is nothing to weight the flows by.
  if (!data || !find(data.columns, (c: any) => c.name === "value")) {
    return false;
  }
  return every(data.rows, (row: any) =>
    every(row, (v: any) => {
      if (!v || isString(v)) {
        return true;
      }
      return isFinite(v);
    })
  );
}

export interface BuiltSankey {
  option: any;
  signature: string;
}

export default function buildOption(data: any): BuiltSankey {
  const rows = prepareDataRows(data.rows);
  if (!isDataValid({ ...data, rows })) {
    return { option: { series: [] }, signature: "invalid" };
  }

  const { nodes, links } = buildGraph(rows);

  // ECharts writes a node's label to its right. For the last column that is off
  // the edge of the canvas, and the label is silently clipped -- "Exit" renders
  // as "E". Those labels go on the inside instead.
  const lastDepth = nodes.reduce((deepest, node) => Math.max(deepest, node.depth), 0);
  const positioned = map(nodes, (node) => (node.depth === lastDepth ? { ...node, label: { position: "left" } } : node));

  const option = {
    ...ECHARTS_MOTION,
    tooltip: {
      trigger: "item",
      confine: true,
      formatter: (params: any) =>
        params.dataType === "edge"
          ? `${params.data.source.split("")[0]} → ${params.data.target.split("")[0]}: ${params.data.value}`
          : `${params.data.displayName}`,
    },
    series: [
      {
        id: "sankey",
        type: "sankey",
        data: positioned,
        links,
        emphasis: { focus: "adjacency" },
        label: { formatter: (params: any) => params.data.displayName },
        lineStyle: { color: "gradient", opacity: 0.4 },
        left: 10,
        right: 10,
        top: 10,
        bottom: 10,
      },
    ],
  };

  // The set of nodes is the shape; the same nodes with new weights can tween.
  return { option, signature: JSON.stringify(map(nodes, "name")) };
}
