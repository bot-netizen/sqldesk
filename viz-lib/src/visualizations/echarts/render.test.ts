/**
 * Draws the visualizations that moved off d3 v3 with the real ECharts, headless.
 *
 * The option-shape tests next to each one cannot tell you whether ECharts
 * understands what they built: an unregistered series type, or a tree ECharts
 * rejects, still produces a perfectly reasonable option object and an empty
 * canvas. This is the check that the picture exists.
 *
 * Uses ECharts' CommonJS build, because `.babelrc` does not reach node_modules
 * and babel-jest therefore will not transform the ESM entry our own barrel
 * imports. Registration is asserted separately, at the bottom.
 */
import fs from "fs";
import path from "path";
import buildSankey from "../sankey/buildOption";
import buildSunburst from "../sunburst/buildOption";
import buildBoxPlot from "../box-plot/buildOption";

// eslint-disable-next-line @typescript-eslint/no-var-requires
const echarts = require("echarts");

function render(option: any) {
  const chart = echarts.init(null, null, { renderer: "svg", ssr: true, width: 600, height: 400 });
  try {
    chart.setOption(option);
    return chart.renderToSVGString() as string;
  } finally {
    chart.dispose();
  }
}

/** Shapes ECharts actually drew, excluding the legend's own swatches. */
function drawnMarks(svg: string) {
  return svg
    .split(/(?=<(?:path|circle|rect|polyline|polygon|line)\b)/)
    .filter((element) => element.includes('ecmeta_ssr_type="chart"')).length;
}

describe("Visualizations -> off d3 v3 -> rendering for real", () => {
  test("a sankey draws its flows", () => {
    const built = buildSankey({
      columns: [{ name: "value" }, { name: "stage1" }, { name: "stage2" }],
      rows: [
        { stage1: "visit", stage2: "signup", value: 40 },
        { stage1: "visit", stage2: "bounce", value: 60 },
        { stage1: "signup", stage2: "purchase", value: 10 },
      ],
    });
    const svg = render(built.option);

    expect(svg.startsWith("<svg")).toBe(true);
    expect(drawnMarks(svg)).toBeGreaterThan(0);
  });

  test("a sunburst draws its rings", () => {
    const built = buildSunburst({
      rows: [
        { stage1: "a", stage2: "b", value: 3 },
        { stage1: "a", stage2: "c", value: 1 },
        { stage1: "d", stage2: null, value: 2 },
      ],
    });
    const svg = render(built.option);

    expect(svg.startsWith("<svg")).toBe(true);
    expect(drawnMarks(svg)).toBeGreaterThan(0);
  });

  test("the deprecated boxplot draws a box per column", () => {
    const built = buildBoxPlot(
      {
        columns: [{ name: "latency" }, { name: "size" }],
        rows: [1, 2, 3, 4, 5].map((n) => ({ latency: n, size: n * 10 })),
      },
      {}
    );
    const svg = render(built.option);

    expect(svg.startsWith("<svg")).toBe(true);
    expect(drawnMarks(svg)).toBeGreaterThan(0);
  });

  test("an empty sankey and an empty sunburst draw nothing, without throwing", () => {
    expect(() => render(buildSankey({ columns: [{ name: "stage1" }], rows: [] }).option)).not.toThrow();
    expect(() => render(buildSunburst({ rows: [] }).option)).not.toThrow();
  });
});

describe("Visualizations -> off d3 v3 -> registration", () => {
  // The renders above use the full ECharts build, so they pass whether or not
  // the series is registered. The app uses a tree-shaken barrel, where an
  // unregistered type draws nothing at all.
  const source = fs.readFileSync(path.join(__dirname, "index.ts"), "utf8");

  test.each([
    ["sankey", "SankeyChart"],
    ["sunburst", "SunburstChart"],
    ["the deprecated boxplot", "BoxplotChart"],
  ])("%s needs %s registered", (_name, chartModule) => {
    expect(source).toContain(chartModule);
  });
});
