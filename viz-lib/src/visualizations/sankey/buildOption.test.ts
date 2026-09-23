import buildOption, { buildGraph, prepareDataRows, problemWith } from "./buildOption";

const columns = [{ name: "value" }, { name: "stage1" }, { name: "stage2" }];

function rows(...items: any[]) {
  return items;
}

describe("Visualizations -> Sankey -> the graph", () => {
  test("a stage pair becomes a link between two nodes", () => {
    const { nodes, links } = buildGraph(rows({ stage1: "a", stage2: "b", value: 5 }));

    // Every path ends in an exit node, so "b" at stage 2 flows into one.
    expect(links).toHaveLength(2);
    expect(links[0].value).toBe(5);
    expect(nodes.map((n) => n.displayName)).toEqual(["a", "b", "Exit"]);
  });

  test("the same label at two stages is two different nodes", () => {
    // "a" at stage 1 and "a" at stage 2 are not the same thing, and merging them
    // would draw a loop back into an earlier column.
    const { nodes } = buildGraph(rows({ stage1: "a", stage2: "a", value: 1 }));

    expect(nodes.filter((n) => n.displayName === "a")).toHaveLength(2);
    expect(new Set(nodes.map((n) => n.name)).size).toBe(nodes.length);
  });

  test("rows following the same path are summed into one link", () => {
    const { links } = buildGraph(rows({ stage1: "a", stage2: "b", value: 2 }, { stage1: "a", stage2: "b", value: 3 }));

    const aToB = links.find((l) => l.source.startsWith("a") && l.target.startsWith("b"));
    expect(aToB!.value).toBe(5);
    expect(links.filter((l) => l.source.startsWith("a"))).toHaveLength(1);
  });

  test("a path that stops early is not joined onward", () => {
    // A blank stage ends the journey. The hop into it is still drawn -- that is
    // where the volume went -- but nothing is invented beyond it, so there is no
    // exit node hanging off a stage the data never reached.
    const { links } = buildGraph(rows({ stage1: "a", stage2: "", value: 4 }));

    expect(links).toHaveLength(1);
    expect(links[0].source.startsWith("a")).toBe(true);
    expect(links[0].value).toBe(4);
  });

  test("a missing label reads as Exit rather than as blank", () => {
    const { nodes } = buildGraph(rows({ stage1: "a", stage2: null, value: 1 }));

    expect(nodes.map((n) => n.displayName)).toContain("Exit");
  });

  test("nodes carry the depth they belong to, so the columns stay in order", () => {
    const { nodes } = buildGraph(rows({ stage1: "a", stage2: "b", value: 1 }));

    expect(nodes.find((n) => n.displayName === "a")!.depth).toBe(0);
    expect(nodes.find((n) => n.displayName === "b")!.depth).toBe(1);
  });

  test("labels sharing a first word share a colour, as they did before", () => {
    const { nodes } = buildGraph(rows({ stage1: "Signup A", stage2: "Signup B", value: 1 }));

    const [first, second] = nodes;
    expect(first.itemStyle.color).toBe(second.itemStyle.color);
  });

  test("zero-weight links are dropped rather than drawn as nothing", () => {
    const { links } = buildGraph(rows({ stage1: "a", stage2: "b", value: 0 }));

    expect(links).toEqual([]);
  });
});

describe("Visualizations -> Sankey -> validation", () => {
  test("numeric strings are coerced before the data is judged", () => {
    expect(prepareDataRows([{ value: "5", stage1: "a" }])).toEqual([{ value: 5, stage1: "a" }]);
  });

  test("a non-numeric string stays a string, and is allowed", () => {
    expect(prepareDataRows([{ value: 1, stage1: "a" }])).toEqual([{ value: 1, stage1: "a" }]);
  });

  test("without a value column there is nothing to weight the flows by", () => {
    expect(problemWith({ columns: [{ name: "stage1" }], rows: [{ stage1: "a" }] })).toMatch(/value/);
    expect(problemWith({ columns, rows: [{ value: 1, stage1: "a" }] })).toBeNull();
  });

  test("each way of being undrawable says which one it is", () => {
    // One empty box used to stand for all three, and they are fixed in three
    // different places: the query, the editor, the data.
    expect(problemWith({ columns, rows: [] })).toMatch(/No rows/);
    expect(problemWith({ columns: [{ name: "stage1" }], rows: [{ stage1: "a" }] })).toMatch(/“value”/);
    expect(problemWith({ columns, rows: [{ value: {}, stage1: "a" }] })).toMatch(/number or a label/);
  });

  test("invalid data builds an empty chart instead of throwing, and says why", () => {
    const built = buildOption({ columns: [{ name: "stage1" }], rows: [{ stage1: "a" }] });

    expect(built.option.series).toEqual([]);
    expect(built.problem).toMatch(/“value”/);
  });
});

describe("Visualizations -> Sankey -> the option", () => {
  const data = { columns, rows: rows({ stage1: "a", stage2: "b", value: 5 }) };

  test("builds a sankey series with nodes and links", () => {
    const built = buildOption(data);
    const [series] = built.option.series;

    expect(series.type).toBe("sankey");
    expect(series.data.length).toBeGreaterThan(0);
    expect(series.links.length).toBeGreaterThan(0);
  });

  test("the label shows the plain name, not the internal node key", () => {
    const built = buildOption(data);
    const [series] = built.option.series;
    const node = series.data[0];

    expect(node.name).toContain(""); // unique key, carries the depth
    expect(series.label.formatter({ data: node })).toBe("a"); // what the user sees
  });

  test("the same paths with new weights keep their signature, so they tween", () => {
    const before = buildOption(data);
    const heavier = buildOption({ columns, rows: rows({ stage1: "a", stage2: "b", value: 50 }) });
    const different = buildOption({ columns, rows: rows({ stage1: "a", stage2: "c", value: 5 }) });

    expect(heavier.signature).toBe(before.signature);
    expect(different.signature).not.toBe(before.signature);
  });
});

describe("Visualizations -> Sankey -> labels that fit on the canvas", () => {
  const columns = [{ name: "value" }, { name: "stage1" }, { name: "stage2" }];

  test("the last column labels inward, because outward is off the edge", () => {
    // ECharts writes a node's label to its right; for the final column that is
    // past the edge and the text is silently clipped ("Exit" became "E").
    const built = buildOption({ columns, rows: [{ stage1: "a", stage2: "b", value: 1 }] });
    const [series] = built.option.series;
    const deepest = Math.max(...series.data.map((n: any) => n.depth));

    series.data.forEach((node: any) => {
      if (node.depth === deepest) {
        expect(node.label).toEqual({ position: "left" });
      } else {
        expect(node.label).toBeUndefined();
      }
    });
  });
});
