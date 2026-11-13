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
  some,
  sortBy,
} from "lodash";
import { ECHARTS_MOTION } from "@/visualizations/shared/motion";
import { NO_ROWS } from "@/visualizations/shared/components/Problem";
import { AllColorPaletteArrays, resolveColorScheme } from "@/visualizations/ColorPalette";

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

/** The palette every sankey had before there was a choice, and still the default. */
export const CLASSIC = "Classic";

/*
  Quieter palettes, asked for because the classic one and the chart palettes
  read as bright on a flow chart, where colour covers most of the area.
  Desaturated and mid-light, still told apart one from the next.

  Soft  -- pastel: dusty blue, apricot, sage, mauve...
  Calm  -- the same hues a step deeper, for a white page that needs contrast.
  Blues -- one hue, light to dark, for a sankey whose colours mean nothing.
*/
export const SANKEY_PALETTES: { [name: string]: string[] } = {
  Soft: ["#7b9cc4", "#e0a77e", "#8fbca5", "#c4a0c4", "#d6c07f", "#8db6c6", "#c69b91", "#a3a5cc", "#a8b78c", "#b5ada0"],
  Calm: ["#5b7ea4", "#c4895f", "#6a9c84", "#9479a1", "#b49d5c", "#5c97a3", "#a46f6a", "#7c84ad", "#8a986a", "#888179"],
  Blues: ["#2f5f8a", "#6e9cc8", "#4a7fb0", "#94b8db", "#3d6f9d", "#b9d1e8", "#5d8ebd", "#82abd3", "#a7c5e2", "#cadcee"],
};

/** What the palette select offers: the classic one, the quiet ones, then the chart palettes. */
export const SANKEY_SCHEMES = [CLASSIC, ...Object.keys(SANKEY_PALETTES), ...Object.keys(AllColorPaletteArrays)];

/*
  How the flows are coloured.

  gradient -- each flow fades from the colour of the stage it leaves to the
              colour of the one it reaches. What every sankey has done; on a
              palette with red and green in it, a flow that is red at one
              end and green at the other reads as a change that is not there.
  source   -- each flow is one colour end to end, the stage it leaves.
  journey  -- each journey keeps the colour of the first stage it started
              from, all the way to the last: the flows from one source can be
              followed across every stage. Later stages are drawn neutral, so
              the colour belongs to the people, not the step.
  target   -- each flow is the colour of the stage it reaches: give the
              outcomes their colours (won, lost) and every flow says where it
              ended up.
  continues -- one colour for every flow that goes on; grey for a flow that
              stops (into Exit) or reaches a stage somebody coloured grey. The
              quietest: the eye goes to what continues.
*/
export const LINK_COLORS = ["gradient", "source", "journey", "target", "continues"] as const;
export type LinkColor = (typeof LINK_COLORS)[number];

/** A neutral for stages that are not the colour of anything in journey mode. */
export const NEUTRAL_NODE = "#a8a29e";

/*
  Where the stages sit across the chart.

  justify -- every path's last stage at the right edge, as before: an exit at
             stage two is drawn beside the outcomes of stage five.
  left    -- each stage in its own column from the left, so a drop-off is
             drawn where it happened.
*/
export const NODE_ALIGNS = ["justify", "left"] as const;
export type NodeAlign = (typeof NODE_ALIGNS)[number];

/*
  Percentages, worked out from the flows rather than read from the query:
  a percentage per row cannot be added up when several rows meet at a stage.

  total    -- of everything at the first stage.
  previous -- of the stages flowing into it: "45% of Signup".
*/
export const NODE_PERCENTS = ["none", "total", "previous"] as const;
export type NodePercent = (typeof NODE_PERCENTS)[number];

/*
  When one flow is most of the total -- bid requests that mostly pass, a
  funnel where nine in ten leave at the first step -- everything else is a
  hairline beside it. Two ways out, both keeping the numbers true:

  hiddenNodes -- labels left out of the drawing. Every flow through them goes
                 too, so the rest fills the chart; percentages are still of
                 the full total, and the chart says what is not drawn.
  widthScale  -- "sqrt" draws each flow's width by the square root of its
                 value, so a flow a hundredth the size is a tenth as wide
                 rather than invisible. Labels and tooltips keep the real
                 numbers, and the chart says the widths are not to scale.
*/
export const WIDTH_SCALES = ["linear", "sqrt"] as const;
export type WidthScale = (typeof WIDTH_SCALES)[number];

export interface SankeySettings {
  colorScheme?: string;
  linkColor?: LinkColor;
  /** Chosen by label, over the palette. */
  nodeColors?: { [label: string]: string | null };
}

function paletteFor(scheme: any): string[] {
  if (!scheme || scheme === CLASSIC) {
    return CATEGORY_20;
  }
  if (SANKEY_PALETTES[scheme]) {
    return SANKEY_PALETTES[scheme];
  }
  return (AllColorPaletteArrays as any)[resolveColorScheme(scheme)] || CATEGORY_20;
}

/** A palette colour per distinct key, in first-seen order, as d3 v3 did. */
function categoryColors(palette: string[] = CATEGORY_20) {
  const assigned = new Map<string, string>();
  return (key: string) => {
    if (!assigned.has(key)) {
      assigned.set(key, palette[assigned.size % palette.length]);
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
  /** When the width is drawn compressed, what the flow is really worth. */
  realValue?: number;
  /** Journey mode: the first-stage label this flow started from. */
  origin?: string;
  lineStyle?: { color: string };
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

export function buildGraph(rows: any[], settings: SankeySettings = {}): { nodes: SankeyNode[]; links: SankeyLink[] } {
  const nodesByKey = new Map<string, SankeyNode>();
  const linksByKey = new Map<string, SankeyLink>();
  const classic = !settings.colorScheme || settings.colorScheme === CLASSIC;
  const palette = paletteFor(settings.colorScheme);
  const color = categoryColors(palette);
  const chosen = settings.nodeColors || {};
  const journeys = settings.linkColor === "journey";
  const continues = settings.linkColor === "continues";
  // The one colour of everything that continues.
  const accent = palette[0];

  function picked(displayName: string): string | null {
    const value = chosen[displayName];
    return isString(value) && value ? value : null;
  }

  const dataKeys = stageOrder(keys(rows[0] || {}));

  function colorOf(displayName: string) {
    const own = picked(displayName);
    if (own) {
      return own;
    }
    if (classic) {
      // d3 coloured by the first word of the label, so "Signup A" and
      // "Signup B" shared a colour. Kept for the classic palette, so a saved
      // sankey looks as it did.
      return color(displayName.replace(/ .*/, ""));
    }
    // A palette somebody chose colours each label -- except Exit, which is
    // where paths stop rather than a category of anything.
    return displayName === "Exit" ? NEUTRAL_NODE : color(displayName);
  }

  /** In "continues": grey where a path stops, the accent everywhere else. */
  function continuesColor(displayName: string) {
    return picked(displayName) || (displayName === "Exit" ? NEUTRAL_NODE : accent);
  }

  function nodeFor(label: any, depth: number) {
    const displayName = normalizeName(label);
    const name = `${displayName}${STAGE}${depth}`;
    let node = nodesByKey.get(name);
    if (!node) {
      const own = colorOf(displayName);
      node = {
        name,
        displayName,
        depth: depth - 1,
        itemStyle: { color: continues ? continuesColor(displayName) : journeys && depth > 1 ? NEUTRAL_NODE : own },
      };
      nodesByKey.set(name, node);
    }
    return node;
  }

  function addLink(sourceLabel: any, targetLabel: any, value: any, depth: number, origin: string) {
    // A blank stage beyond the first means the path stopped earlier; joining it
    // onward would invent a journey nobody took.
    if ((sourceLabel === "" || !sourceLabel) && depth > 1) {
      return;
    }
    const source = nodeFor(sourceLabel, depth);
    const target = nodeFor(targetLabel, depth + 1);
    // In journey mode, one flow per starting point so each keeps its colour;
    // ECharts lays several flows between the same two stages side by side.
    const pair = `${source.name}${target.name}`;
    const key = journeys ? `${pair}${origin}` : pair;
    const existing = linksByKey.get(key);
    const amount = parseInt(value, 10) || 0;
    if (existing) {
      existing.value += amount;
    } else {
      const link: SankeyLink = { source: source.name, target: target.name, value: amount };
      if (journeys) {
        link.origin = origin;
        link.lineStyle = { color: colorOf(origin) };
      } else if (continues) {
        link.lineStyle = { color: continuesColor(target.displayName) };
      }
      linksByKey.set(key, link);
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
    const origin = normalizeName(row[dataKeys[0]]);
    for (let depth = 1; depth < stages; depth += 1) {
      addLink(row[dataKeys[depth - 1]], row[dataKeys[depth]], row.value || 0, depth, origin);
    }
    // Ensures the last stage has a corresponding exit node.
    addLink(row[dataKeys[stages - 1]], null, row.value || 0, stages, origin);
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
  /** Said under the chart: what is left out, or that widths are not to scale. */
  note?: string | null;
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

/** A share as people write one: 45%, 4.5%, and never 0% for something that is there. */
export function formatPercent(ratio: number): string {
  if (!isFinite(ratio) || ratio <= 0) {
    return "0%";
  }
  if (ratio < 0.001) {
    return "<0.1%";
  }
  const percent = ratio * 100;
  const text = percent >= 10 ? percent.toFixed(0) : percent.toFixed(1).replace(/\.0$/, "");
  return `${text}%`;
}

export interface Shares {
  /** Everything at the first stage: what "of the total" is of. */
  total: number;
  /** Of the total, by node name. */
  ofTotal: Map<string, number>;
  /** Of the stages flowing into it, by node name. Absent at the first stage. */
  ofPrevious: Map<string, number>;
  /** The stages flowing into each node, by name, for saying what "previous" was. */
  sources: Map<string, string[]>;
}

/**
 * Each stage's share of the total, and of the stages that flow into it.
 *
 * Worked out from the flows: the query has one row per path, and a
 * percentage per row cannot be added up where several rows meet.
 */
export function nodeShares(nodes: SankeyNode[], links: SankeyLink[], values: Map<string, number>): Shares {
  const total = nodes.filter((node) => node.depth === 0).reduce((sum, node) => sum + (values.get(node.name) || 0), 0);
  const sources = new Map<string, string[]>();
  each(links, (link) => {
    const from = sources.get(link.target) || [];
    if (from.indexOf(link.source) < 0) {
      from.push(link.source);
    }
    sources.set(link.target, from);
  });
  const ofTotal = new Map<string, number>();
  const ofPrevious = new Map<string, number>();
  each(nodes, (node) => {
    const value = values.get(node.name) || 0;
    ofTotal.set(node.name, total > 0 ? value / total : 0);
    const from = sources.get(node.name);
    if (from && from.length > 0) {
      const before = from.reduce((sum, name) => sum + (values.get(name) || 0), 0);
      ofPrevious.set(node.name, before > 0 ? value / before : 0);
    }
  });
  return { total, ofTotal, ofPrevious, sources };
}

function labelOf(name: string) {
  return name.split(STAGE)[0];
}

function pick<T extends string>(value: any, allowed: readonly T[], fallback: T): T {
  return (allowed as readonly string[]).indexOf(value) >= 0 ? (value as T) : fallback;
}

export default function buildOption(data: any, options: any = {}): BuiltSankey {
  const rows = prepareDataRows(data.rows);
  const problem = problemWith({ ...data, rows });
  if (problem) {
    return { option: { series: [] }, signature: "invalid", problem };
  }

  const linkColor = pick<LinkColor>(options.linkColor, LINK_COLORS, "gradient");
  const nodeAlign = pick<NodeAlign>(options.nodeAlign, NODE_ALIGNS, "justify");
  const colorScheme = SANKEY_SCHEMES.indexOf(options.colorScheme) >= 0 ? options.colorScheme : CLASSIC;
  const { nodes, links } = buildGraph(rows, { colorScheme, linkColor, nodeColors: options.nodeColors });

  // What each stage is worth, and its shares, from everything -- including
  // what is left out of the drawing, so "of the total" stays the total.
  const values = nodeValues(nodes, links);
  const showValues = options.showNodeValues === true;
  const percent = pick<NodePercent>(options.nodePercent, NODE_PERCENTS, "none");
  const flowLabels = options.flowLabels === true;
  const shares = nodeShares(nodes, links, values);

  const hidden = new Set<string>(filter(options.hiddenNodes, (label: any) => isString(label) && label !== ""));
  const widthScale = pick<WidthScale>(options.widthScale, WIDTH_SCALES, "linear");
  const shown = filter(links, (link) => !hidden.has(labelOf(link.source)) && !hidden.has(labelOf(link.target)));
  if (shown.length === 0) {
    return {
      option: { series: [] },
      signature: "everything-hidden",
      problem: "Every flow is left out. Take something off “Leave out” in the editor to draw the rest.",
    };
  }
  const drawn =
    widthScale === "sqrt"
      ? map(shown, (link) => ({ ...link, value: Math.sqrt(link.value), realValue: link.value }))
      : shown;
  const used = new Set<string>();
  each(drawn, (link) => {
    used.add(link.source);
    used.add(link.target);
  });
  const drawnNodes = filter(nodes, (node) => used.has(node.name));

  // ECharts writes a node's label to its right. For the last column that is off
  // the edge of the canvas, and the label is silently clipped -- "Exit" renders
  // as "E". Those labels go on the inside instead.
  const lastDepth = drawnNodes.reduce((deepest, node) => Math.max(deepest, node.depth), 0);
  const positioned = map(drawnNodes, (node) =>
    node.depth === lastDepth ? { ...node, label: { position: "left" } } : node
  );

  // Said on the chart itself, so it is in an exported picture and a Slack
  // one too: a drawing with something missing, or out of proportion, has
  // to say so where it is looked at.
  const notes: string[] = [];
  const left = Array.from(hidden).filter((label) => some(nodes, (node) => node.displayName === label));
  if (left.length > 0) {
    const described = left.map((label) => {
      const share = nodes
        .filter((node) => node.displayName === label)
        .reduce((most, node) => Math.max(most, shares.ofTotal.get(node.name) || 0), 0);
      return `${label} (${formatPercent(share)} of the total)`;
    });
    notes.push(`Not drawn: ${described.join(", ")}`);
  }
  if (widthScale === "sqrt") {
    notes.push("Widths compressed so small flows show; numbers are real");
  }
  const note = notes.length > 0 ? notes.join(" · ") : null;

  /** "45%" for a stage, by the measure the editor chose, or null. */
  function stagePercent(name: string): string | null {
    if (percent === "total") {
      return formatPercent(shares.ofTotal.get(name) || 0);
    }
    if (percent === "previous") {
      // The first stage has nothing before it; its share of the total is the
      // only share it has.
      const share = shares.ofPrevious.has(name) ? shares.ofPrevious.get(name) : shares.ofTotal.get(name);
      return formatPercent(share || 0);
    }
    return null;
  }

  /** What a flow is really worth, however wide it is drawn. */
  function worth(link: any): number {
    return link.realValue !== undefined ? link.realValue : link.value;
  }

  /** A flow's share of the stage it leaves: "45% of Signup". */
  function flowShare(link: any): number {
    const from = values.get(link.source) || 0;
    return from > 0 ? worth(link) / from : 0;
  }

  const nodeTooltip = (node: any) => {
    // The value is in the tooltip whether or not the labels show it: hovering
    // a node to find out what it is worth should not depend on a display
    // setting. So are both shares -- they cost nothing to read here.
    const value = values.get(node.name);
    const name = escapeHtml(node.displayName);
    if (value === undefined) {
      return name;
    }
    const parts = [`${name}: ${escapeHtml(formatNodeValue(value))}`];
    if (shares.total > 0 && node.depth > 0) {
      parts.push(`${formatPercent(shares.ofTotal.get(node.name) || 0)} of the total`);
      const from = shares.sources.get(node.name) || [];
      if (shares.ofPrevious.has(node.name) && from.length > 0) {
        const before = from.length === 1 ? escapeHtml(labelOf(from[0])) : "the stage before";
        parts.push(`${formatPercent(shares.ofPrevious.get(node.name) || 0)} of ${before}`);
      }
    } else if (shares.total > 0 && nodes.filter((n) => n.depth === 0).length > 1) {
      parts.push(`${formatPercent(shares.ofTotal.get(node.name) || 0)} of the total`);
    }
    return parts.join(" · ");
  };

  const linkTooltip = (link: any) => {
    const from = escapeHtml(labelOf(link.source));
    const to = escapeHtml(labelOf(link.target));
    const parts = [`${from} → ${to}: ${escapeHtml(formatNodeValue(worth(link)))}`];
    if (link.origin !== undefined) {
      parts[0] += ` from ${escapeHtml(link.origin)}`;
    }
    parts.push(`${formatPercent(flowShare(link))} of ${from}`);
    if (shares.total > 0) {
      parts.push(`${formatPercent(worth(link) / shares.total)} of the total`);
    }
    return parts.join(" · ");
  };

  const option = {
    ...ECHARTS_MOTION,
    tooltip: {
      trigger: "item",
      confine: true,
      formatter: (params: any) => (params.dataType === "edge" ? linkTooltip(params.data) : nodeTooltip(params.data)),
    },
    series: [
      {
        id: "sankey",
        type: "sankey",
        data: positioned,
        links: drawn,
        // Hovering a stage or a flow lights every journey through it, first
        // stage to last -- not just its neighbours, which is a step of a path
        // rather than the path.
        emphasis: { focus: "trajectory" },
        nodeAlign,
        // With values and percentages on, the labels of the last two columns
        // ran into each other ("Exit 46,000 4.6%" over "Exit 54,000 5.4%"),
        // and a flow's label could land on a stage's. One that would overlap
        // is left off; the tooltip still has it.
        labelLayout: { hideOverlap: true },
        label: {
          formatter: (params: any) => {
            const parts = [params.data.displayName];
            const value = values.get(params.data.name);
            if (showValues && value !== undefined) {
              parts.push(formatNodeValue(value));
            }
            const share = stagePercent(params.data.name);
            if (share) {
              parts.push(share);
            }
            return parts.join("  ");
          },
        },
        // Each flow's share of the stage it leaves, on the flow. Off by
        // default: on a busy funnel it is a wall of numbers.
        edgeLabel: {
          show: flowLabels,
          fontSize: 11,
          // Plain dark text. ECharts outlines a label in the colour of what it
          // sits on, which over a dark flow came out blue and blurred.
          color: "#44403c",
          textBorderWidth: 0,
          formatter: (params: any) => formatPercent(flowShare(params.data)),
        },
        // Journey flows carry their own colour; the others take it from the
        // stages at either end, or from the one they leave.
        lineStyle: {
          color: linkColor === "source" || linkColor === "target" ? linkColor : "gradient",
          opacity: linkColor === "journey" || linkColor === "continues" ? 0.5 : 0.4,
        },
        left: 10,
        right: 10,
        top: 10,
        // Room for the note under the flows, when there is one.
        bottom: note ? 30 : 10,
      },
    ],
    ...(note
      ? {
          title: {
            text: note,
            left: 10,
            bottom: 4,
            textStyle: { fontSize: 11, fontWeight: "normal", color: "#78716c" },
          },
        }
      : {}),
  };

  // The set of nodes is the shape; the same nodes with new weights can tween.
  // What the labels say and how the flows are coloured are part of the shape
  // too: without them in the signature ECharts merges the new option over the
  // old one and the labels and colours never change.
  return {
    option,
    signature: JSON.stringify([
      showValues,
      percent,
      flowLabels,
      colorScheme,
      linkColor,
      options.nodeColors || null,
      Array.from(hidden),
      widthScale,
      nodeAlign,
      map(drawnNodes, "name"),
    ]),
    problem: null,
    note,
  };
}
