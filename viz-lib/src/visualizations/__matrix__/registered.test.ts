import fs from "fs";
import path from "path";

import { SHAPES } from "./dataShapes";
import { VARIANTS } from "./optionVariants";

import boxPlotOptions from "../box-plot";
import buildBoxPlot from "../box-plot/buildOption";
import calendarOptions from "../calendar/getOptions";
import buildCalendar from "../calendar/buildOption";
import chartOptions from "../chart/getOptions";
import getChartData from "../chart/getChartData";
import buildChart from "../chart/echarts/buildOption";
import gaugeOptions from "../gauge/getOptions";
import buildGauge from "../gauge/buildOption";
import histogramOptions from "../histogram/getOptions";
import buildHistogram from "../histogram/buildOption";
import progressOptions from "../progress/getOptions";
import buildProgress from "../progress/buildOption";
import radarOptions from "../radar/getOptions";
import buildRadar from "../radar/buildOption";
import buildSankey from "../sankey/buildOption";
import buildSunburst from "../sunburst/buildOption";
import timelineOptions from "../timeline/getOptions";
import buildTimeline from "../timeline/buildOption";
import treemapOptions from "../treemap/getOptions";
import buildTreemap from "../treemap/buildOption";
import waterfallOptions from "../waterfall/getOptions";
import buildWaterfall from "../waterfall/buildOption";

/*
  ECharts is registered piece by piece -- `echarts/core` plus the exact series
  and components we draw with -- because the full build is 1.07MB and most of
  it is chart types we do not have. The cost of that is silence: an option
  that names a component nobody registered is ignored, with no warning, no
  throw, and nothing on the canvas.

  That is how the gauge's reading tile shipped with the ends of its range
  invisible. It writes them with `graphic`, `GraphicComponent` was not
  registered, and every test passed -- because a test renders with
  `require("echarts")`, which is the *whole* library and has everything in it.

  So this checks the option against the registrations rather than against a
  renderer: whatever a built option asks for has to be imported somewhere the
  visualization's own chunk will reach.
*/

const SUBJECTS: [string, string, (data: any, options: any, size: any) => any, (o: any, d: any) => any][] = [
  ["BOXPLOT", "box-plot", (d, o) => buildBoxPlot(d, o), (o) => (boxPlotOptions as any).getOptions(o)],
  ["CALENDAR_HEATMAP", "calendar", (d, o, s) => buildCalendar(d, o, s), calendarOptions],
  ["CHART", "chart", (d, o, s) => buildChart(getChartData(d.rows, o), o, s), (o) => chartOptions(o)],
  ["GAUGE", "gauge", (d, o, s) => buildGauge(d, o, s), gaugeOptions],
  ["HISTOGRAM", "histogram", (d, o) => buildHistogram(d, o), histogramOptions],
  ["PROGRESS", "progress", (d, o) => buildProgress(d, o), progressOptions],
  ["RADAR", "radar", (d, o, s) => buildRadar(d, o, s), radarOptions],
  ["SANKEY", "sankey", (d) => buildSankey(d), (o) => o || {}],
  ["SUNBURST_SEQUENCE", "sunburst", (d) => buildSunburst(d), (o) => o || {}],
  ["STATE_TIMELINE", "timeline", (d, o) => buildTimeline(d, o), timelineOptions],
  ["TREEMAP", "treemap", (d, o) => buildTreemap(d, o), treemapOptions],
  ["WATERFALL", "waterfall", (d, o) => buildWaterfall(d, o), waterfallOptions],
];

/** Top-level option keys that only work when their component is registered. */
const COMPONENT_FOR_KEY: Record<string, string> = {
  angleAxis: "PolarComponent",
  aria: "AriaComponent",
  brush: "BrushComponent",
  calendar: "CalendarComponent",
  dataZoom: "DataZoomComponent",
  geo: "GeoComponent",
  graphic: "GraphicComponent",
  grid: "GridComponent",
  legend: "LegendComponent",
  parallel: "ParallelComponent",
  polar: "PolarComponent",
  radar: "RadarComponent",
  radiusAxis: "PolarComponent",
  singleAxis: "SingleAxisComponent",
  timeline: "TimelineComponent",
  title: "TitleComponent",
  toolbox: "ToolboxComponent",
  tooltip: "TooltipComponent",
  visualMap: "VisualMapComponent",
  xAxis: "GridComponent",
  yAxis: "GridComponent",
};

/** Series-level keys with a component behind them. */
const COMPONENT_FOR_SERIES_KEY: Record<string, string> = {
  markArea: "MarkAreaComponent",
  markLine: "MarkLineComponent",
  markPoint: "MarkPointComponent",
};

const SRC = path.join(__dirname, "..");

function sourceOf(...dirs: string[]): string {
  let text = "";
  for (const dir of dirs) {
    const full = path.join(SRC, dir);
    for (const name of fs.readdirSync(full)) {
      const file = path.join(full, name);
      if (fs.statSync(file).isFile() && /\.(ts|tsx)$/.test(name) && !name.includes(".test.")) {
        text += fs.readFileSync(file, "utf8");
      }
    }
  }
  return text;
}

/** What the shared chunk registers, which every visualization gets. */
const SHARED = sourceOf("echarts");

function registrationsFor(dir: string): string {
  // A visualization's own folder, plus the renderer sub-folder the funnel
  // keeps its drawn shape in.
  const dirs = [dir];
  if (fs.existsSync(path.join(SRC, dir, "Renderer")) && fs.statSync(path.join(SRC, dir, "Renderer")).isDirectory()) {
    dirs.push(path.join(dir, "Renderer"));
  }
  return SHARED + sourceOf(...dirs);
}

function componentsUsedBy(option: any): Set<string> {
  const needed = new Set<string>();
  if (!option || typeof option !== "object") {
    return needed;
  }
  for (const key of Object.keys(option)) {
    if (COMPONENT_FOR_KEY[key] && option[key] !== undefined && option[key] !== null) {
      needed.add(COMPONENT_FOR_KEY[key]);
    }
  }
  for (const series of Array.isArray(option.series) ? option.series : []) {
    for (const key of Object.keys(series || {})) {
      if (COMPONENT_FOR_SERIES_KEY[key] && series[key]) {
        needed.add(COMPONENT_FOR_SERIES_KEY[key]);
      }
    }
  }
  return needed;
}

const SIZE = { width: 420, height: 260 };

describe("what an option asks for is what the bundle registers", () => {
  test.each(SUBJECTS)("%s", (type, dir, build, getOptions) => {
    const source = registrationsFor(dir);
    const missing = new Set<string>();

    let built = 0;
    for (const shape of SHAPES) {
      const data = { columns: shape.columns, rows: shape.rows };
      for (const variant of (VARIANTS as any)[type] || [{ name: "default", options: {} }]) {
        let option;
        try {
          const result = build(data, getOptions(variant.options, data), SIZE);
          if (result.problem) {
            continue;
          }
          option = result.option;
        } catch (e) {
          continue; // what it does with awkward data is drawing.test.ts's business
        }
        built += 1;
        for (const component of componentsUsedBy(option)) {
          if (!source.includes(component)) {
            missing.add("{}: {}".replace("{}", variant.name).replace("{}", component));
          }
        }
      }
    }

    expect([...missing]).toEqual([]);
    // A visualization that refused every shape would pass while checking
    // nothing, which is how this test first passed against the bug it exists
    // for -- the data was being read out of the wrong property.
    expect(built).toBeGreaterThan(0);
  });

  test("the map is not empty, so a passing test means something", () => {
    expect(Object.keys(COMPONENT_FOR_KEY).length).toBeGreaterThan(10);
    expect(SHARED).toContain("GridComponent");
  });
});
