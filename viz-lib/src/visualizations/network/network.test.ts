import getOptions from "./getOptions";
import buildOption, { buildGraph, edgeWidth, nodeSize, problemWith } from "./buildOption";

/*
  Who is connected to whom.

  The catalog could draw a flow through ordered stages, a hierarchy and a
  share of a whole. It could not draw a plain relationship -- accounts
  that trade with each other, services that call each other -- because
  those have no left-to-right order, and the sankey invents one.
*/
const columns = [{ name: "from" }, { name: "to" }, { name: "weight" }];

function options(overrides: any = {}) {
  return getOptions({ sourceColumn: "from", targetColumn: "to", valueColumn: "weight", ...overrides }, {
    columns,
    rows: [],
  } as any);
}

const edge = (from: string, to: string, weight: number) => ({ from, to, weight });

describe("the network", () => {
  describe("what it refuses to draw", () => {
    test("no rows", () => {
      expect(problemWith({ rows: [] }, options())).toBeTruthy();
    });

    // The same column twice is a graph of self-loops, which draws as a
    // pile of dots and reads as broken data.
    test("both ends being the same column", () => {
      expect(problemWith({ rows: [{}] }, options({ targetColumn: "from" }))).toContain("different columns");
    });

    test("and nothing wrong with a configured graph", () => {
      expect(problemWith({ rows: [{}] }, options())).toBeNull();
    });
  });

  describe("building the graph", () => {
    test("a node per name, an edge per pair", () => {
      const { nodes, edges } = buildGraph([edge("a", "b", 1), edge("b", "c", 2)], options());

      expect(nodes.map((n) => n.id).sort()).toEqual(["a", "b", "c"]);
      expect(edges).toHaveLength(2);
    });

    // Drawn twice, once each way, it looks like twice the traffic.
    test("undirected, a→b and b→a are one connection", () => {
      const { edges } = buildGraph([edge("a", "b", 3), edge("b", "a", 4)], options());

      expect(edges).toHaveLength(1);
      expect(edges[0].value).toBe(7);
    });

    test("directed, they are two", () => {
      const { edges } = buildGraph([edge("a", "b", 3), edge("b", "a", 4)], options({ directed: true }));

      expect(edges).toHaveLength(2);
    });

    test("two rows for the same pair are one heavier connection", () => {
      const { edges } = buildGraph([edge("a", "b", 3), edge("a", "b", 4)], options());

      expect(edges).toHaveLength(1);
      expect(edges[0].value).toBe(7);
    });

    // Both directions, which is what makes "the busiest node" mean
    // anything when the edges have no direction.
    test("a node weighs everything through it, in either direction", () => {
      const { nodes } = buildGraph([edge("a", "b", 3), edge("c", "b", 4)], options());

      expect(nodes.find((n) => n.id === "b")!.weight).toBe(7);
    });

    test("with no weight column every connection counts once", () => {
      // Raw rather than through getOptions, which fills an empty weight
      // column back in from whatever numeric column it can find.
      const unweighted = { ...options(), valueColumn: "" };
      const { edges } = buildGraph([edge("a", "b", 99)], unweighted);

      expect(edges[0].value).toBe(1);
    });

    test("a row missing an end is not half a connection", () => {
      const { nodes, edges } = buildGraph([{ from: "a", to: null, weight: 1 }], options());

      expect(nodes).toEqual([]);
      expect(edges).toEqual([]);
    });
  });

  describe("how big things are drawn", () => {
    // Read as width, weight is read as area by eye: linear widths make a
    // ten-times edge look a hundred times heavier.
    test("sizes go by the square root, not straight off the number", () => {
      const quarter = edgeWidth(25, 100);
      const full = edgeWidth(100, 100);

      expect(full).toBeGreaterThan(quarter);
      expect(quarter).toBeCloseTo(1 + 5 * 0.5);
    });

    test("nothing to scale against is still a drawable size", () => {
      expect(edgeWidth(0, 0)).toBe(1);
      expect(nodeSize(0, 0, true)).toBe(18);
    });

    test("turning sizing off makes every node the same", () => {
      expect(nodeSize(5, 100, false)).toBe(nodeSize(100, 100, false));
    });

    test("the busiest node is the biggest", () => {
      expect(nodeSize(100, 100, true)).toBeGreaterThan(nodeSize(10, 100, true));
    });
  });

  describe("the option it builds", () => {
    const data = { columns, rows: [edge("a", "b", 1), edge("b", "c", 2)] };

    test("is a force-laid graph", () => {
      const series = buildOption(data, options()).option.series[0];

      expect(series.type).toBe("graph");
      expect(series.layout).toBe("force");
    });

    test("arrowheads only where direction means something", () => {
      expect(buildOption(data, options()).option.series[0].edgeSymbol).toEqual(["none", "none"]);
      expect(buildOption(data, options({ directed: true })).option.series[0].edgeSymbol).toEqual(["none", "arrow"]);
    });

    // Left running, a force graph drifts for as long as the tab is open,
    // which on a dashboard is a chart that will not hold still.
    test("a big graph settles instead of animating forever", () => {
      const many = { columns, rows: Array.from({ length: 200 }, (_, i) => edge(`n${i}`, `n${i + 1}`, 1)) };

      expect(buildOption(many, options()).option.series[0].force.layoutAnimation).toBe(false);
      expect(buildOption(data, options()).option.series[0].force.layoutAnimation).toBe(true);
    });

    test("hovering a node dims everything it is not connected to", () => {
      expect(buildOption(data, options()).option.series[0].emphasis.focus).toBe("adjacency");
    });

    test("a different set of nodes is a different shape", () => {
      const other = { columns, rows: [edge("x", "y", 1)] };

      expect(buildOption(data, options()).signature).not.toBe(buildOption(other, options()).signature);
    });
  });
});
