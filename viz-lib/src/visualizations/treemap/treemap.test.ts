import buildTree, { treeDepth, UNNAMED } from "./tree";
import getOptions from "./getOptions";
import buildOption from "./buildOption";

/*
  A treemap divides an area by size, so every rectangle's meaning depends on
  the total being right. Double-counting a row, or dropping a level of the
  path, produces a treemap that looks entirely plausible and is wrong about
  every proportion on it -- which is why the tree is built and tested apart
  from the drawing.
*/

const columns = [
  { name: "region", type: "string" },
  { name: "product", type: "string" },
  { name: "revenue", type: "float" },
];

const rows = [
  { region: "North", product: "Team", revenue: 100 },
  { region: "North", product: "Starter", revenue: 40 },
  { region: "South", product: "Team", revenue: 60 },
];

describe("buildTree", () => {
  test("groups down the path and sums at the leaves", () => {
    const tree = buildTree(rows, ["region", "product"], "revenue");
    expect(tree.nodes.map((n) => n.name)).toEqual(["North", "South"]);
    expect(tree.nodes[0].children!.map((n) => [n.name, n.value])).toEqual([
      ["Team", 100],
      ["Starter", 40],
    ]);
    expect(tree.total).toBe(200);
  });

  test("rows sharing a full path are added together, not drawn twice", () => {
    const tree = buildTree(
      [
        { region: "North", product: "Team", revenue: 10 },
        { region: "North", product: "Team", revenue: 15 },
      ],
      ["region", "product"],
      "revenue"
    );
    expect(tree.nodes[0].children).toHaveLength(1);
    expect(tree.nodes[0].children![0].value).toBe(25);
    expect(tree.total).toBe(25);
  });

  test("one path column is a flat treemap", () => {
    const tree = buildTree(rows, ["region"], "revenue");
    expect(tree.nodes.map((n) => [n.name, n.value])).toEqual([
      ["North", 140],
      ["South", 60],
    ]);
    expect(treeDepth(tree.nodes)).toBe(1);
  });

  test("each node knows how deep it sits and how it was reached", () => {
    const tree = buildTree(rows, ["region", "product"], "revenue");
    expect(tree.nodes[0].depth).toBe(1);
    expect(tree.nodes[0].path).toEqual(["North"]);
    expect(tree.nodes[0].children![0].depth).toBe(2);
    expect(tree.nodes[0].children![0].path).toEqual(["North", "Team"]);
  });

  test("zero and negative sizes are left out, and counted", () => {
    // A rectangle of zero area is no rectangle, and a negative one would have
    // to take area from its neighbours.
    const tree = buildTree(
      [
        { region: "A", revenue: 10 },
        { region: "B", revenue: 0 },
        { region: "C", revenue: -5 },
        { region: "D", revenue: "n/a" },
      ],
      ["region"],
      "revenue"
    );
    expect(tree.nodes.map((n) => n.name)).toEqual(["A"]);
    expect(tree.skipped).toBe(3);
    expect(tree.total).toBe(10);
  });

  test("a blank part way down the path is named, not dropped", () => {
    // Dropping it would move that row's value up a level and overstate its
    // parent against every sibling.
    const tree = buildTree([{ region: "North", product: null, revenue: 10 }], ["region", "product"], "revenue");
    expect(tree.nodes[0].children![0].name).toBe(UNNAMED);
    expect(tree.total).toBe(10);
  });

  test("a row with nothing to group by is counted separately", () => {
    const tree = buildTree(
      [
        { region: null, product: null, revenue: 10 },
        { region: "North", product: "Team", revenue: 5 },
      ],
      ["region", "product"],
      "revenue"
    );
    expect(tree.unplaced).toBe(1);
    expect(tree.total).toBe(5);
  });

  test("numbers used as groups still group", () => {
    const tree = buildTree([{ year: 2024, revenue: 10 }], ["year"], "revenue");
    expect(tree.nodes[0].name).toBe("2024");
  });

  test("no rows is an empty tree, not a crash", () => {
    expect(buildTree([], ["region"], "revenue")).toEqual({ nodes: [], total: 0, skipped: 0, unplaced: 0 });
  });
});

describe("treeDepth", () => {
  test("counts the levels actually present", () => {
    expect(treeDepth(buildTree(rows, ["region", "product"], "revenue").nodes)).toBe(2);
    expect(treeDepth([])).toBe(0);
  });
});

describe("the treemap", () => {
  function build(overrides: any = {}, data: any = { columns, rows }) {
    return buildOption(
      data,
      getOptions({ pathColumns: ["region", "product"], valueColumn: "revenue", ...overrides }, data)
    );
  }

  test("branches carry no value of their own, so ECharts sums their children", () => {
    // A branch given both a value and children double-counts in the layout.
    const north = build().option.series[0].data[0];
    expect(north.value).toBeUndefined();
    expect(north.children.map((c: any) => c.value)).toEqual([100, 40]);
  });

  test("drilling in is offered only when there is something below", () => {
    expect(build({ visibleDepth: 1 }).option.series[0].nodeClick).toBe("zoomToNode");
    expect(build({ pathColumns: ["region"] }).option.series[0].nodeClick).toBe(false);
  });

  test("the tooltip gives the full path and the share of the whole", () => {
    const built = build();
    const tooltip = built.option.tooltip.formatter({
      value: 100,
      name: "Team",
      treePathInfo: [{ name: "" }, { name: "North" }, { name: "Team" }],
    });
    expect(tooltip).toContain("North → Team");
    expect(tooltip).toContain("50.0%");
  });

  test("says what it had to leave out", () => {
    const built = build({}, { columns, rows: [...rows, { region: "X", product: "Y", revenue: -1 }] });
    expect(built.note).toContain("1 row had no positive number");
  });

  describe("when there is nothing to draw", () => {
    test("no rows", () => {
      expect(build({}, { columns, rows: [] }).problem).toBe("No rows to show.");
    });

    test("no grouping column", () => {
      expect(build({ pathColumns: ["gone"] }).problem).toBe("Choose at least one grouping column in the editor.");
    });

    test("no size column", () => {
      expect(build({ valueColumn: "gone" }).problem).toBe("Choose a size column in the editor.");
    });

    test("nothing positive to size by", () => {
      const built = build({}, { columns, rows: [{ region: "A", product: "B", revenue: 0 }] });
      expect(built.problem).toContain("no positive numbers");
    });
  });

  test("new sizes for the same rectangles can tween; a new grouping redraws", () => {
    const same = build().signature;
    const alsoSame = buildOption(
      { columns, rows: rows.map((r) => ({ ...r, revenue: r.revenue * 2 })) },
      getOptions({ pathColumns: ["region", "product"], valueColumn: "revenue" }, { columns, rows })
    ).signature;
    const different = build({ pathColumns: ["product", "region"] }).signature;
    expect(alsoSame).toBe(same);
    expect(different).not.toBe(same);
  });
});
