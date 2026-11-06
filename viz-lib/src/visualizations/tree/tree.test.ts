import getOptions from "./getOptions";
import buildOption, { ROOT_NAME, problemWith, toEChartsTree } from "./buildOption";
import buildTree from "../treemap/tree";

/*
  A hierarchy drawn as a hierarchy.

  The treemap and the sunburst both show one and both spend their area on
  size, so a small branch under a large one is a sliver you cannot read.
  The shape of the hierarchy itself -- how deep it goes, which branch is a
  chain and which is a fan -- is exactly what nesting hides.

  This spends its space on the structure instead: a leaf worth nothing
  takes the same room as a leaf worth millions.
*/
const columns = [{ name: "region" }, { name: "channel" }, { name: "revenue" }];

function options(overrides: any = {}) {
  return getOptions({ pathColumns: ["region", "channel"], valueColumn: "revenue", ...overrides }, {
    columns,
    rows: [],
  } as any);
}

const row = (region: string, channel: string, revenue: number) => ({ region, channel, revenue });

const DATA = {
  columns,
  rows: [row("north", "paid", 10), row("north", "organic", 5), row("south", "paid", 7)],
};

describe("the tree", () => {
  describe("what it refuses to draw", () => {
    test("no rows", () => {
      expect(problemWith({ rows: [] }, options())).toBeTruthy();
    });

    test("no hierarchy chosen", () => {
      expect(problemWith({ rows: [{}] }, { ...options(), pathColumns: [] })).toContain("hierarchy");
    });

    test("no value chosen", () => {
      expect(problemWith({ rows: [{}] }, { ...options(), valueColumn: "" })).toContain("worth");
    });

    test("and nothing wrong with a configured tree", () => {
      expect(problemWith({ rows: [{}] }, options())).toBeNull();
    });
  });

  // Two builders would be two sets of rules about empty levels and
  // duplicate names, and a path that groups one way in a treemap has to
  // group the same way here.
  describe("the hierarchy is the treemap's", () => {
    test("built by the same function, so the grouping matches", () => {
      const shared = buildTree(DATA.rows, ["region", "channel"], "revenue");

      expect(shared.nodes.map((n) => n.name).sort()).toEqual(["north", "south"]);
      expect(shared.nodes.find((n) => n.name === "north")!.children).toHaveLength(2);
    });
  });

  describe("folding", () => {
    test("branches deeper than asked for start folded, not hidden", () => {
      const { nodes } = buildTree(DATA.rows, ["region", "channel"], "revenue");
      const converted = toEChartsTree(nodes, 1, (node) => node.name);

      expect(converted[0].collapsed).toBe(true);
      // Still there to open.
      expect(converted[0].children).toHaveLength(2);
    });

    test("branches within the depth stay open", () => {
      const { nodes } = buildTree(DATA.rows, ["region", "channel"], "revenue");
      const converted = toEChartsTree(nodes, 2, (node) => node.name);

      expect(converted[0].collapsed).toBe(false);
    });

    test("a leaf is never folded, having nothing to fold", () => {
      const { nodes } = buildTree(DATA.rows, ["region"], "revenue");
      const converted = toEChartsTree(nodes, 1, (node) => node.name);

      expect(converted[0].collapsed).toBe(false);
    });
  });

  describe("the option it builds", () => {
    test("is a tree series", () => {
      expect(buildOption(DATA, options()).option.series[0].type).toBe("tree");
    });

    // A query returns several top-level branches; ECharts takes one root.
    // Without a root that is not drawn, only the first branch appears and
    // it looks like the data is missing.
    test("several top-level branches are gathered under one unnamed root", () => {
      const series = buildOption(DATA, options()).option.series[0];

      expect(series.data).toHaveLength(1);
      expect(series.data[0].name).toBe(ROOT_NAME);
      expect(series.data[0].children).toHaveLength(2);
    });

    test("the direction is the one that was asked for", () => {
      expect(buildOption(DATA, options()).option.series[0].layout).toBe("orthogonal");
      expect(buildOption(DATA, options({ layout: "radial" })).option.series[0].layout).toBe("radial");
      expect(buildOption(DATA, options({ layout: "vertical" })).option.series[0].orient).toBe("TB");
    });

    test("values appear beside names only when asked", () => {
      const without = buildOption(DATA, options()).option.series[0].data[0].children;
      const with_ = buildOption(DATA, options({ showValues: true })).option.series[0].data[0].children;

      expect(without[0].name).not.toMatch(/\d/);
      expect(with_[0].name).toMatch(/\d/);
    });

    // How you follow one path out of a crowded tree.
    test("hovering lifts the whole branch", () => {
      expect(buildOption(DATA, options()).option.series[0].emphasis.focus).toBe("descendant");
    });

    test("changing the layout changes the shape", () => {
      expect(buildOption(DATA, options()).signature).not.toBe(
        buildOption(DATA, options({ layout: "radial" })).signature
      );
    });
  });

  describe("the options it normalises", () => {
    test("an unknown direction falls back to left-to-right", () => {
      expect(options({ layout: "sideways" }).layout).toBe("horizontal");
    });

    test("depth is held between one and six", () => {
      expect(options({ initialDepth: 0 }).initialDepth).toBe(1);
      expect(options({ initialDepth: 99 }).initialDepth).toBe(6);
    });

    // `Number(null)` is 0 and finite, so an absent option would clamp to
    // the minimum rather than fall back.
    test("an absent depth is the default, not the shallowest", () => {
      expect(options({ initialDepth: null }).initialDepth).toBe(2);
      expect(options({ initialDepth: "" }).initialDepth).toBe(2);
    });
  });
});
