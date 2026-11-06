import { each, map, sortBy } from "lodash";
import escapeHtml from "@/lib/escapeHtml";
import { ECHARTS_MOTION } from "@/visualizations/shared/motion";
import { NO_ROWS } from "@/visualizations/shared/components/Problem";
import { createNumberFormatter } from "@/lib/value-format";
import { NetworkOptions } from "./getOptions";

/*
  Who is connected to whom.

  The catalog could draw a flow through ordered stages -- that is the
  sankey -- and a hierarchy, and a share of a whole. It could not draw a
  plain relationship: accounts that trade with each other, services that
  call each other, tags that co-occur. Those have no left-to-right order to
  lay out along, and forcing them into one invents a direction the data
  does not have.

  Laid out by force, so the shape comes from the connections rather than
  from a decision somebody made about ordering. The same data always
  settles the same way, because the layout is seeded from the node order
  and the node order comes from the rows.
*/

export interface NetworkNode {
  id: string;
  name: string;
  /** Everything through this node, which is what its size means. */
  weight: number;
  symbolSize: number;
  label?: { show: boolean };
}

export interface NetworkEdge {
  source: string;
  target: string;
  value: number;
  lineStyle: { width: number };
}

export interface BuiltNetwork {
  option: any;
  signature: string;
  problem: string | null;
}

export function problemWith(data: any, options: NetworkOptions): string | null {
  if (!data || !data.rows || data.rows.length === 0) {
    return NO_ROWS;
  }
  if (!options.sourceColumn || !options.targetColumn) {
    return "This needs two columns: one for each end of a connection.";
  }
  if (options.sourceColumn === options.targetColumn) {
    return "The two ends need to be different columns.";
  }
  return null;
}

/** How wide to draw an edge carrying `value`, against the heaviest one. */
export function edgeWidth(value: number, heaviest: number): number {
  if (!heaviest || heaviest <= 0) {
    return 1;
  }
  // Square-rooted, like the node sizes: weight read as width is read as
  // area by eye, and linear widths make a ten-times edge look hundredfold.
  return 1 + 5 * Math.sqrt(Math.max(0, value) / heaviest);
}

/** How big to draw a node, against the busiest one. */
export function nodeSize(weight: number, heaviest: number, sizeByWeight: boolean): number {
  if (!sizeByWeight || !heaviest || heaviest <= 0) {
    return 18;
  }
  return 10 + 34 * Math.sqrt(Math.max(0, weight) / heaviest);
}

/**
 * Rows into a graph.
 *
 * Edges are summed per pair, because two rows joining the same pair are one
 * heavier connection and not two lines drawn on top of each other. A node's
 * weight is everything through it, both directions, which is what makes
 * "the busiest one" mean anything on an undirected graph.
 */
export function buildGraph(rows: any[], options: NetworkOptions): { nodes: NetworkNode[]; edges: NetworkEdge[] } {
  const weights = new Map<string, number>();
  const pairs = new Map<string, { source: string; target: string; value: number }>();

  each(rows, (row) => {
    const source = String(row[options.sourceColumn] ?? "");
    const target = String(row[options.targetColumn] ?? "");
    if (!source || !target) {
      return;
    }
    const raw = options.valueColumn ? Number(row[options.valueColumn]) : 1;
    const value = Number.isFinite(raw) ? raw : 0;

    // Undirected, a→b and b→a are the same connection. Keyed on the sorted
    // pair so they are added together rather than drawn twice, once each
    // way, which looks like twice the traffic.
    const ends = options.directed ? [source, target] : sortBy([source, target]);
    const key = `${ends[0]}\u0000${ends[1]}`;
    const existing = pairs.get(key);
    if (existing) {
      existing.value += value;
    } else {
      pairs.set(key, { source: ends[0], target: ends[1], value });
    }

    weights.set(source, (weights.get(source) || 0) + value);
    weights.set(target, (weights.get(target) || 0) + value);
  });

  const heaviestNode = Math.max(0, ...Array.from(weights.values()));
  const heaviestEdge = Math.max(0, ...Array.from(pairs.values()).map((pair) => pair.value));

  const nodes: NetworkNode[] = map(Array.from(weights.entries()), ([name, weight]) => ({
    id: name,
    name,
    weight,
    symbolSize: nodeSize(weight, heaviestNode, options.sizeByWeight),
    label: { show: options.showLabels },
  }));

  const edges: NetworkEdge[] = map(Array.from(pairs.values()), (pair) => ({
    source: pair.source,
    target: pair.target,
    value: pair.value,
    lineStyle: { width: edgeWidth(pair.value, heaviestEdge) },
  }));

  return { nodes, edges };
}

export default function buildOption(data: any, rawOptions: NetworkOptions): BuiltNetwork {
  const problem = problemWith(data, rawOptions);
  if (problem) {
    return { option: { series: [] }, signature: "invalid", problem };
  }

  const { nodes, edges } = buildGraph(data.rows, rawOptions);
  const format = createNumberFormatter(rawOptions.valueFormat);

  const option = {
    ...ECHARTS_MOTION,
    tooltip: {
      trigger: "item",
      confine: true,
      formatter: (params: any) =>
        params.dataType === "edge"
          ? `${escapeHtml(params.data.source)} — ${escapeHtml(params.data.target)}: ${escapeHtml(
              format(params.data.value)
            )}`
          : `${escapeHtml(params.data.name)}: ${escapeHtml(format(params.data.weight))}`,
    },
    series: [
      {
        id: "network",
        type: "graph",
        layout: "force",
        data: nodes,
        edges,
        roam: true,
        draggable: true,
        // Hovering a node dims everything it is not connected to, which on a
        // dense graph is the only way to read one node's neighbourhood.
        emphasis: { focus: "adjacency", lineStyle: { width: 4 } },
        label: { position: "right", formatter: (params: any) => params.data.name },
        edgeSymbol: rawOptions.directed ? ["none", "arrow"] : ["none", "none"],
        edgeSymbolSize: 8,
        lineStyle: { color: "source", opacity: 0.45, curveness: rawOptions.directed ? 0.1 : 0 },
        force: {
          repulsion: 220,
          edgeLength: [60, 160],
          gravity: 0.08,
          // Settle and stop. Left running, a force graph drifts for as long
          // as the tab is open, which on a dashboard is a chart that will
          // not hold still long enough to read.
          friction: 0.2,
          layoutAnimation: nodes.length <= 120,
        },
      },
    ],
  };

  // The nodes are the shape; the same nodes with new weights can tween.
  return { option, signature: JSON.stringify(map(nodes, "id")), problem: null };
}
