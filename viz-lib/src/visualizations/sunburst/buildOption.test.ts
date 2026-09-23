import buildOption, { buildHierarchy, isDataValid } from "./buildOption";

const EXIT = "<<<Exit>>>";

/** Every node in the tree, depth first. */
function flatten(items: any[]): any[] {
  return items.reduce((all, item) => all.concat([item], flatten(item.children || [])), [] as any[]);
}

describe("Visualizations -> Sunburst -> the hierarchy", () => {
  test("a table row becomes a path through the stages", () => {
    const root = buildHierarchy([{ stage1: "a", stage2: "b", value: 3 }]);
    const [first] = root.children;

    expect(first.name).toBe("a");
    expect(first.children.map((c: any) => c.name)).toContain("b");
  });

  test("rows sharing a prefix share the branch", () => {
    const root = buildHierarchy([
      { stage1: "a", stage2: "b", value: 1 },
      { stage1: "a", stage2: "c", value: 2 },
    ]);

    expect(root.children.filter((c: any) => c.name === "a")).toHaveLength(1);
    const names = root.children.find((c: any) => c.name === "a").children.map((c: any) => c.name);
    expect(names).toEqual(expect.arrayContaining(["b", "c"]));
  });

  test("the hierarchy format is read as well as the table format", () => {
    const root = buildHierarchy([
      { sequence: 1, stage: 1, node: "a", value: 4 },
      { sequence: 1, stage: 2, node: "b", value: 4 },
    ]);

    expect(root.children[0].name).toBe("a");
  });

  test("a stage column with no value does not become an empty ring", () => {
    const root = buildHierarchy([{ stage1: "a", stage2: null, value: 1 }]);

    expect(flatten(root.children).map((n) => n.name)).not.toContain(null);
  });
});

describe("Visualizations -> Sunburst -> the option", () => {
  const data = {
    rows: [
      { stage1: "a", stage2: "b", value: 3 },
      { stage1: "a", stage2: "c", value: 1 },
    ],
  };

  test("builds a sunburst series", () => {
    const [series] = buildOption(data).option.series;

    expect(series.type).toBe("sunburst");
    expect(series.data.length).toBeGreaterThan(0);
  });

  test("no rows says so rather than drawing an empty box", () => {
    const built = buildOption({ rows: [] });

    expect(built.option.series).toEqual([]);
    expect(built.problem).toMatch(/No rows/);
    expect(isDataValid({ rows: [] })).toBe(false);
  });

  test("a chart that drew has nothing to say", () => {
    expect(buildOption({ rows: [{ stage1: "a", value: 1 }] }).problem).toBeNull();
  });

  test("a path that ends keeps its share of the arc, but is not drawn", () => {
    // Exit nodes appear where journeys of different lengths share a prefix:
    // some people stopped at "a", others carried on to "b", and the ones who
    // stopped still own their slice of a's ring.
    const ragged = {
      rows: [
        { stage1: "a", stage2: null, value: 5 },
        { stage1: "a", stage2: "b", value: 3 },
      ],
    };
    const [series] = buildOption(ragged).option.series;
    const exits = flatten(series.data).filter((n) => n.name === EXIT);

    expect(exits.length).toBeGreaterThan(0);
    exits.forEach((node) => {
      expect(node.itemStyle.color).toBe("transparent");
      expect(node.label.show).toBe(false);
      expect(node.silent).toBe(true);
    });
  });

  test("a leaf carries its own count; a branch is summed from its children", () => {
    const [series] = buildOption(data).option.series;
    const branch = series.data.find((n: any) => n.name === "a");

    expect(branch.value).toBeUndefined();
    expect(branch.children.every((c: any) => c.children || typeof c.value === "number")).toBe(true);
  });

  test("the same paths with new counts keep their signature, so they tween", () => {
    const before = buildOption(data);
    const heavier = buildOption({
      rows: [
        { stage1: "a", stage2: "b", value: 30 },
        { stage1: "a", stage2: "c", value: 10 },
      ],
    });
    const different = buildOption({ rows: [{ stage1: "a", stage2: "d", value: 3 }] });

    expect(heavier.signature).toBe(before.signature);
    expect(different.signature).not.toBe(before.signature);
  });
});
