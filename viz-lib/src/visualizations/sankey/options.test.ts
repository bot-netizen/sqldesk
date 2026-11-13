import { AllColorPaletteArrays } from "@/visualizations/ColorPalette";
import buildOption, {
  NEUTRAL_NODE,
  SANKEY_PALETTES,
  SANKEY_SCHEMES,
  STAGE,
  buildGraph,
  formatPercent,
  nodeShares,
  nodeValues,
} from "./buildOption";

/*
  Colours somebody can choose, percentages worked out from the flows, and two
  ways to stop one enormous flow making hairlines of the rest -- asked for on
  an ad-tech sankey where nine bid requests in ten pass.
*/

const columns = [{ name: "value" }, { name: "stage1" }, { name: "stage2" }, { name: "stage3" }];

// 1,000 bid requests: 900 pass, 100 are chosen, of which 60 win and 40 lose.
const BIDS = {
  columns,
  rows: [
    { stage1: "Bid requests", stage2: "Bid passes", stage3: null, value: 900 },
    { stage1: "Bid requests", stage2: "Bid chosen", stage3: "Won", value: 60 },
    { stage1: "Bid requests", stage2: "Bid chosen", stage3: "Lost", value: 40 },
  ],
};

// Two places people came from, meeting at one stage.
const SOURCES = {
  columns: [{ name: "value" }, { name: "stage1" }, { name: "stage2" }],
  rows: [
    { stage1: "Search", stage2: "Signup", value: 30 },
    { stage1: "Ads", stage2: "Signup", value: 20 },
  ],
};

function series(built: any) {
  return built.option.series[0];
}

function node(built: any, label: string) {
  return series(built).data.find((n: any) => n.displayName === label);
}

function label(built: any, name: string) {
  return series(built).label.formatter({ data: node(built, name) });
}

describe("a sankey's colours", () => {
  test("are the classic ones unless somebody chooses", () => {
    const classic = buildGraph(SOURCES.rows);
    const chosen = buildGraph(SOURCES.rows, { colorScheme: "Classic" });

    expect(classic.nodes.map((n) => n.itemStyle.color)).toEqual(chosen.nodes.map((n) => n.itemStyle.color));
    expect(classic.nodes[0].itemStyle.color).toBe("#1f77b4");
  });

  test("come from the palette chosen, one per label", () => {
    const palette = (AllColorPaletteArrays as any)["Tableau 10"];
    const { nodes } = buildGraph(
      [
        { stage1: "Signup A", stage2: "Signup B", value: 1 },
        { stage1: "Signup C", stage2: "Signup B", value: 1 },
      ],
      { colorScheme: "Tableau 10" }
    );
    const colours = nodes.filter((n) => n.displayName !== "Exit").map((n) => n.itemStyle.color);

    colours.forEach((colour) => expect(palette).toContain(colour));
    // Not by first word, as the classic palette does: three labels, three colours.
    expect(new Set(colours).size).toBe(3);
  });

  test("leave Exit grey on a chosen palette: it is where paths stop, not a category", () => {
    const { nodes } = buildGraph(SOURCES.rows, { colorScheme: "Soft" });
    const exit = nodes.find((n) => n.displayName === "Exit")!;

    expect(exit.itemStyle.color).toBe(NEUTRAL_NODE);
    // The classic palette colours it, as it always did.
    expect(buildGraph(SOURCES.rows).nodes.find((n) => n.displayName === "Exit")!.itemStyle.color).not.toBe(
      NEUTRAL_NODE
    );
  });

  test("include quiet ones, softer than the chart palettes", () => {
    const { nodes } = buildGraph(SOURCES.rows, { colorScheme: "Calm" });

    expect(SANKEY_PALETTES.Calm).toContain(nodes[0].itemStyle.color);
    expect(SANKEY_SCHEMES.slice(0, 4)).toEqual(["Classic", "Soft", "Calm", "Blues"]);
  });

  test("can be chosen label by label", () => {
    const { nodes } = buildGraph(SOURCES.rows, { nodeColors: { Ads: "#123456" } });

    expect(nodes.find((n) => n.displayName === "Ads")!.itemStyle.color).toBe("#123456");
  });
});

describe("a sankey's flows", () => {
  test("fade from one stage's colour to the next, as they always have", () => {
    expect(series(buildOption(SOURCES)).lineStyle.color).toBe("gradient");
  });

  test("can be one colour end to end, the stage they leave", () => {
    expect(series(buildOption(SOURCES, { linkColor: "source" })).lineStyle.color).toBe("source");
  });

  describe("coloured by journey", () => {
    const built = buildOption(SOURCES, { linkColor: "journey" });
    const { nodes } = buildGraph(SOURCES.rows, { linkColor: "journey" });
    const colourOf = (name: string) => nodes.find((n) => n.displayName === name)!.itemStyle.color;

    test("keep the colour of where they started, all the way to the end", () => {
      const intoExit = series(built).links.filter((link: any) => link.target.startsWith("Exit"));

      // One flow per starting point between the same two stages, each its own colour.
      expect(intoExit).toHaveLength(2);
      expect(intoExit.map((link: any) => link.lineStyle.color).sort()).toEqual(
        [colourOf("Ads"), colourOf("Search")].sort()
      );
    });

    test("and the stages after the first are neutral, so the colour is the journey's", () => {
      expect(colourOf("Signup")).toBe(NEUTRAL_NODE);
      expect(colourOf("Search")).not.toBe(NEUTRAL_NODE);
    });

    test("without changing what any stage is worth", () => {
      const signup = `Signup${STAGE}2`;
      const plain = buildGraph(SOURCES.rows);
      const journey = buildGraph(SOURCES.rows, { linkColor: "journey" });

      expect(nodeValues(journey.nodes, journey.links).get(signup)).toBe(50);
      expect(nodeValues(plain.nodes, plain.links).get(signup)).toBe(50);
    });

    test("the tooltip says which journey a flow is", () => {
      const link = series(built).links.find((l: any) => l.origin === "Ads" && l.target.startsWith("Exit"));
      expect(built.option.tooltip.formatter({ dataType: "edge", data: link })).toContain("from Ads");
    });
  });
});

describe("percentages", () => {
  test("are written the way people write them", () => {
    expect(formatPercent(0.9)).toBe("90%");
    expect(formatPercent(0.06)).toBe("6%");
    expect(formatPercent(0.045)).toBe("4.5%");
    expect(formatPercent(0.0004)).toBe("<0.1%");
    expect(formatPercent(0)).toBe("0%");
  });

  test("are of the total, and of the stages flowing in", () => {
    const { nodes, links } = buildGraph(BIDS.rows);
    const shares = nodeShares(nodes, links, nodeValues(nodes, links));
    const won = `Won${STAGE}3`;

    expect(shares.total).toBe(1000);
    expect(shares.ofTotal.get(won)).toBeCloseTo(0.06);
    expect(shares.ofPrevious.get(won)).toBeCloseTo(0.6);
  });

  test("are not on the labels until asked for", () => {
    expect(label(buildOption(BIDS), "Won")).toBe("Won");
  });

  test("of the total, on each stage", () => {
    expect(label(buildOption(BIDS, { nodePercent: "total" }), "Won")).toBe("Won  6%");
  });

  test("of the stage before, on each stage", () => {
    expect(label(buildOption(BIDS, { nodePercent: "previous" }), "Won")).toBe("Won  60%");
    // The first stage has nothing before it: its share of the total.
    expect(label(buildOption(BIDS, { nodePercent: "previous" }), "Bid requests")).toBe("Bid requests  100%");
  });

  test("beside the value, when both are asked for", () => {
    expect(label(buildOption(BIDS, { showNodeValues: true, nodePercent: "total" }), "Bid passes")).toBe(
      "Bid passes  900  90%"
    );
  });

  test("are in the tooltip either way", () => {
    const built = buildOption(BIDS);
    const won = node(built, "Won");

    expect(built.option.tooltip.formatter({ dataType: "node", data: won })).toBe(
      "Won: 60 · 6% of the total · 60% of Bid chosen"
    );
  });

  test("a flow's tooltip says its share of the stage it leaves", () => {
    const built = buildOption(BIDS);
    const link = series(built).links.find((l: any) => l.target.startsWith("Won"));

    expect(built.option.tooltip.formatter({ dataType: "edge", data: link })).toBe(
      "Bid chosen → Won: 60 · 60% of Bid chosen · 6% of the total"
    );
  });

  test("can be written on the flows too", () => {
    const off = series(buildOption(BIDS));
    const on = series(buildOption(BIDS, { flowLabels: true }));
    const link = on.links.find((l: any) => l.target.startsWith("Bid passes"));

    expect(off.edgeLabel.show).toBe(false);
    expect(on.edgeLabel.show).toBe(true);
    expect(on.edgeLabel.formatter({ data: link })).toBe("90%");
  });
});

describe("one flow that dwarfs the rest", () => {
  describe("left out", () => {
    const built = buildOption(BIDS, { hiddenNodes: ["Bid passes"], nodePercent: "total" });

    test("is not drawn, nor is anything through it", () => {
      const names = series(built).data.map((n: any) => n.displayName);

      expect(names).not.toContain("Bid passes");
      expect(series(built).links.some((l: any) => l.source.startsWith("Bid passes"))).toBe(false);
      // The exit only the passed bids reached goes with them.
      expect(series(built).data.filter((n: any) => n.displayName === "Exit")).toHaveLength(1);
    });

    test("while the percentages stay of the full total", () => {
      expect(label(built, "Bid chosen")).toBe("Bid chosen  10%");
      expect(label(built, "Bid requests")).toBe("Bid requests  100%");
    });

    test("and the chart says what is missing, on the picture itself", () => {
      expect(built.note).toBe("Not drawn: Bid passes (90% of the total)");
      expect(built.option.title.text).toBe(built.note);
      expect(series(built).bottom).toBeGreaterThan(10);
    });

    test("a label that is not in the result is not reported", () => {
      expect(buildOption(BIDS, { hiddenNodes: ["Nothing like it"] }).note).toBeNull();
    });

    test("leaving out everything says so instead of drawing nothing", () => {
      const all = buildOption(BIDS, { hiddenNodes: ["Bid requests", "Bid passes", "Bid chosen", "Won", "Lost"] });
      expect(all.problem).toContain("Every flow is left out");
      // Leaving out a first stage leaves the flows that never touch it.
      expect(buildOption(BIDS, { hiddenNodes: ["Bid requests"] }).problem).toBeNull();
    });
  });

  describe("compressed", () => {
    const built = buildOption(BIDS, { widthScale: "sqrt" });
    const passes = series(built).links.find((l: any) => l.target.startsWith("Bid passes"));

    test("is drawn narrower, so the small flows show", () => {
      expect(passes.value).toBeCloseTo(30);
      expect(passes.realValue).toBe(900);
    });

    test("with the real numbers everywhere they are read", () => {
      expect(built.option.tooltip.formatter({ dataType: "edge", data: passes })).toBe(
        "Bid requests → Bid passes: 900 · 90% of Bid requests · 90% of the total"
      );
      expect(label(buildOption(BIDS, { widthScale: "sqrt", showNodeValues: true }), "Bid passes")).toBe(
        "Bid passes  900"
      );
    });

    test("and says the widths are not to scale", () => {
      expect(built.note).toContain("Widths compressed");
    });
  });
});

describe("changing any of these", () => {
  test("redraws rather than merging into the old chart", () => {
    const signatures = [
      {},
      { nodePercent: "total" },
      { flowLabels: true },
      { colorScheme: "Tableau 10" },
      { linkColor: "journey" },
      { nodeColors: { Won: "#000000" } },
      { hiddenNodes: ["Bid passes"] },
      { widthScale: "sqrt" },
    ].map((options) => buildOption(BIDS, options).signature);

    expect(new Set(signatures).size).toBe(signatures.length);
  });

  test("an option nobody recognises draws the default", () => {
    const built = buildOption(BIDS, {
      linkColor: "rainbow",
      nodePercent: "lots",
      widthScale: "log",
      colorScheme: "Nope",
    });

    expect(built.signature).toBe(buildOption(BIDS).signature);
  });
});

describe("flows coloured by where they go", () => {
  test("take the colour of the stage they reach, so outcomes can be coloured", () => {
    expect(series(buildOption(BIDS, { linkColor: "target" })).lineStyle.color).toBe("target");
  });

  describe("in one colour for what continues", () => {
    const options = { linkColor: "continues", colorScheme: "Calm", nodeColors: { "Bid passes": NEUTRAL_NODE } };
    const built = buildOption(BIDS, options);
    const into = (label: string) => series(built).links.find((l: any) => l.target.startsWith(label));
    const accent = SANKEY_PALETTES.Calm[0];

    test("flows that go on share one colour", () => {
      expect(into("Bid chosen").lineStyle.color).toBe(accent);
      expect(into("Won").lineStyle.color).toBe(accent);
    });

    test("flows that stop, or reach a stage coloured grey, are grey", () => {
      expect(into("Exit").lineStyle.color).toBe(NEUTRAL_NODE);
      expect(into("Bid passes").lineStyle.color).toBe(NEUTRAL_NODE);
    });

    test("and so are those stages", () => {
      expect(node(built, "Bid passes").itemStyle.color).toBe(NEUTRAL_NODE);
      expect(node(built, "Bid chosen").itemStyle.color).toBe(accent);
    });
  });
});

describe("where the stages sit", () => {
  test("last stages at the right edge, as before", () => {
    expect(series(buildOption(BIDS)).nodeAlign).toBe("justify");
  });

  test("or each in its own column from the left, so a drop-off is drawn where it happened", () => {
    expect(series(buildOption(BIDS, { nodeAlign: "left" })).nodeAlign).toBe("left");
    expect(buildOption(BIDS, { nodeAlign: "left" }).signature).not.toBe(buildOption(BIDS).signature);
  });
});

test("hovering lights the whole journey, not only the next step", () => {
  expect(series(buildOption(BIDS)).emphasis.focus).toBe("trajectory");
});

test("labels that would overlap are left to the tooltip", () => {
  expect(series(buildOption(BIDS)).labelLayout).toEqual({ hideOverlap: true });
});

test("a flow's label is plain dark text, not outlined in the flow's colour", () => {
  const edgeLabel = series(buildOption(BIDS, { flowLabels: true })).edgeLabel;
  expect(edgeLabel.textBorderWidth).toBe(0);
  expect(edgeLabel.color).toBe("#44403c");
});
