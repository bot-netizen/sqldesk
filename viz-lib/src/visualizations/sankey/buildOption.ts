import escapeHtml from "@/lib/escapeHtml";
import {
  each,
  every,
  filter,
  find,
  isFinite,
  isNaN,
  isNil,
  isNumber,
  isString,
  keys,
  map,
  mapValues,
  sortBy,
} from "lodash";
import { ECHARTS_MOTION } from "@/visualizations/shared/motion";
import { NO_ROWS } from "@/visualizations/shared/components/Problem";

// The data shape is the inherited one: stage columns plus a `value` column,
// one row per path through the stages. Inherited except for the count --
// five was hard-coded in the loop, and is now however many the query
// returns.

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

/*
  Between a node's label and its stage in the name ECharts keys it by.
  Invisible, and legal in XML: the control character used before ended up in
  the chart's aria-label, and one character XML forbids anywhere in a widget
  makes its exported SVG unreadable -- the whole widget missing from a PDF.
*/
export const STAGE = "\u2063";

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
/**
 * The stage columns, left to right.
 *
 * Sorted by the number in the name where there is one, so `stage10` follows
 * `stage9` instead of `stage1`. A plain alphabetical sort was fine while
 * five was the limit and becomes a scrambled funnel the moment somebody
 * needs ten -- the flows still draw, in the wrong order, which is the kind
 * of wrong that gets believed.
 *
 * Columns with no number keep their alphabetical place among themselves and
 * sort before the numbered ones, so a query using plain names is unchanged.
 */
export function stageOrder(columns: string[]): string[] {
  const stages = filter(columns, (key) => key !== "value");
  return sortBy(stages, [
    (key: string) => {
      const digits = /(\d+)\s*$/.exec(key);
      return digits ? 1 : 0;
    },
    (key: string) => {
      const digits = /(\d+)\s*$/.exec(key);
      return digits ? parseInt(digits[1], 10) : 0;
    },
    (key: string) => key,
  ]);
}

export function buildGraph(rows: any[]): { nodes: SankeyNode[]; links: SankeyLink[] } {
  const nodesByKey = new Map<string, SankeyNode>();
  const linksByKey = new Map<string, SankeyLink>();
  const color = categoryColors();

  const dataKeys = stageOrder(keys(rows[0] || {}));

  function nodeFor(label: any, depth: number) {
    const displayName = normalizeName(label);
    const name = `${displayName}${STAGE}${depth}`;
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

  // However many stage columns the query returned. This used to count to
  // five and stop, whatever it was given: a funnel with eight stages drew
  // its first five and silently dropped the rest, which looks like the
  // query is wrong rather than the chart. Ad funnels in particular run
  // long -- impression, bid, win, render, view, click, visit, convert is
  // eight before anybody mentions attribution.
  const stages = dataKeys.length;
  rows.forEach((row: any) => {
    for (let depth = 1; depth < stages; depth += 1) {
      addLink(row[dataKeys[depth - 1]], row[dataKeys[depth]], row.value || 0, depth);
    }
    // Ensures the last stage has a corresponding exit node.
    addLink(row[dataKeys[stages - 1]], null, row.value || 0, stages);
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

/**
 * Why this data cannot be drawn, in words for the reader -- or null.
 *
 * Split out of `isDataValid` because an empty box tells nobody which of the
 * three things is wrong, and the three are fixed in different places: the
 * query, the editor, the data.
 */
export function problemWith(data: any): string | null {
  if (!data || !data.rows || data.rows.length === 0) {
    return NO_ROWS;
  }
  // Without a `value` column there is nothing to weight the flows by.
  if (!find(data.columns, (c: any) => c.name === "value")) {
    return "This needs a column named “value”: it is what weights the flows.";
  }
  const allNumeric = every(data.rows, (row: any) =>
    every(row, (v: any) => {
      if (!v || isString(v)) {
        return true;
      }
      return isFinite(v);
    })
  );
  return allNumeric ? null : "Every value must be a number or a label.";
}

export interface BuiltSankey {
  option: any;
  signature: string;
  /** Said to the reader, instead of an empty box. Null when there is a chart. */
  problem: string | null;
}

/**
 * What each node is worth: everything flowing into it, or for the first
 * column, everything flowing out.
 *
 * Read off the links rather than the rows because that is what the chart
 * actually draws -- a row whose path stops early contributes to the stages
 * it reached and not to the ones it did not, and the links already encode
 * that. Summing the rows per column would count a dropped path as if it had
 * gone the distance.
 */
export function nodeValues(nodes: SankeyNode[], links: SankeyLink[]): Map<string, number> {
  const incoming = new Map<string, number>();
  const outgoing = new Map<string, number>();
  each(links, (link) => {
    incoming.set(link.target, (incoming.get(link.target) || 0) + link.value);
    outgoing.set(link.source, (outgoing.get(link.source) || 0) + link.value);
  });
  const values = new Map<string, number>();
  each(nodes, (node) => {
    const into = incoming.get(node.name);
    values.set(node.name, into === undefined ? outgoing.get(node.name) || 0 : into);
  });
  return values;
}

/** Thousands separated, which is the whole point of putting it on the chart. */
export function formatNodeValue(value: number): string {
  return value.toLocaleString("en-US");
}

export default function buildOption(data: any, options: any = {}): BuiltSankey {
  const rows = prepareDataRows(data.rows);
  const problem = problemWith({ ...data, rows });
  if (problem) {
    return { option: { series: [] }, signature: "invalid", problem };
  }

  const { nodes, links } = buildGraph(rows);

  // ECharts writes a node's label to its right. For the last column that is off
  // the edge of the canvas, and the label is silently clipped -- "Exit" renders
  // as "E". Those labels go on the inside instead.
  const lastDepth = nodes.reduce((deepest, node) => Math.max(deepest, node.depth), 0);
  const positioned = map(nodes, (node) => (node.depth === lastDepth ? { ...node, label: { position: "left" } } : node));

  // What each stage is worth, on the stage. Off by default: on a wide funnel
  // the numbers are what makes it unreadable, and on a narrow one they are
  // the first thing anybody asks for.
  const values = nodeValues(nodes, links);
  const showValues = options.showNodeValues === true;

  const option = {
    ...ECHARTS_MOTION,
    tooltip: {
      trigger: "item",
      confine: true,
      formatter: (params: any) =>
        params.dataType === "edge"
          ? `${escapeHtml(params.data.source.split(STAGE)[0])} → ${escapeHtml(params.data.target.split(STAGE)[0])}: ${escapeHtml(
              params.data.value
            )}`
          : (() => {
              // The value is in the tooltip whether or not the labels show
              // it: hovering a node to find out what it is worth should not
              // depend on a display setting.
              const value = values.get(params.data.name);
              const name = escapeHtml(params.data.displayName);
              return value === undefined ? name : `${name}: ${escapeHtml(formatNodeValue(value))}`;
            })(),
    },
    series: [
      {
        id: "sankey",
        type: "sankey",
        data: positioned,
        links,
        emphasis: { focus: "adjacency" },
        label: {
          formatter: (params: any) => {
            const name = params.data.displayName;
            if (!showValues) {
              return name;
            }
            const value = values.get(params.data.name);
            return value === undefined ? name : `${name}  ${formatNodeValue(value)}`;
          },
        },
        lineStyle: { color: "gradient", opacity: 0.4 },
        left: 10,
        right: 10,
        top: 10,
        bottom: 10,
      },
    ],
  };

  // The set of nodes is the shape; the same nodes with new weights can tween.
  // The toggle is part of the shape: without it in the signature ECharts
  // merges the new option over the old one and the labels never change.
  return { option, signature: JSON.stringify([showValues, map(nodes, "name")]), problem: null };
}
