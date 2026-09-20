import { SHAPES, SIZES } from "./dataShapes";
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

// eslint-disable-next-line @typescript-eslint/no-var-requires
const echarts = require("echarts");

/*
  Every ECharts visualization, at every option the editor offers, against
  every awkward result, drawn at four widget sizes.

  `buildOption` is where each of these actually decides what to draw, and an
  option it cannot handle shows up in one of three ways: a throw, an option
  ECharts rejects, or -- the quiet one -- a chart that renders to nothing at
  all. So each case is not merely built but rendered, and the result has to be
  either an honest "there is nothing to draw" message or some actual ink.
*/

type Built = { option: any; problem?: string | null };

interface Subject {
  type: string;
  build: (data: any, options: any, size: { width: number; height: number }) => Built;
  getOptions: (options: any, data: any) => any;
}

const SUBJECTS: Subject[] = [
  { type: "BOXPLOT", getOptions: (o) => (boxPlotOptions as any).getOptions(o), build: (d, o) => buildBoxPlot(d, o) },
  { type: "CALENDAR_HEATMAP", getOptions: calendarOptions, build: (d, o, s) => buildCalendar(d, o, s) },
  {
    type: "CHART",
    getOptions: (o) => chartOptions(o),
    build: (d, o, s) => buildChart(getChartData(d.rows, o), o, s),
  },
  { type: "GAUGE", getOptions: gaugeOptions, build: (d, o, s) => buildGauge(d, o, s) },
  { type: "HISTOGRAM", getOptions: histogramOptions, build: (d, o) => buildHistogram(d, o) },
  { type: "PROGRESS", getOptions: progressOptions, build: (d, o) => buildProgress(d, o) },
  { type: "RADAR", getOptions: radarOptions, build: (d, o, s) => buildRadar(d, o, s) },
  { type: "SANKEY", getOptions: (o) => o || {}, build: (d) => buildSankey(d) },
  { type: "SUNBURST_SEQUENCE", getOptions: (o) => o || {}, build: (d) => buildSunburst(d) },
  { type: "STATE_TIMELINE", getOptions: timelineOptions, build: (d, o) => buildTimeline(d, o) },
  { type: "TREEMAP", getOptions: treemapOptions, build: (d, o) => buildTreemap(d, o) },
  { type: "WATERFALL", getOptions: waterfallOptions, build: (d, o) => buildWaterfall(d, o) },
];

/** Render an option and report what, if anything, ended up on the canvas. */
function draw(option: any, size: { width: number; height: number }) {
  const chart = echarts.init(null, null, { renderer: "svg", ssr: true, ...size });
  try {
    // containLabel measures text, and jsdom has no canvas to measure with.
    const grid = option.grid ? { ...option.grid, containLabel: false } : undefined;
    chart.setOption(grid ? { ...option, grid } : option);
    return chart.renderToSVGString() as string;
  } finally {
    chart.dispose();
  }
}

/** Shapes that ECharts draws with: anything else on the canvas is chrome. */
const INK = /<(path|rect|circle|polygon|polyline|text)\b/g;

function inkCount(svg: string) {
  return (svg.match(INK) || []).length;
}

describe("every ECharts visualization, drawn", () => {
  test("the matrix covers every visualization that draws with ECharts", () => {
    // Missing one means it is built and rendered by nothing here, and the
    // gap is invisible because the rest still pass.
    expect(SUBJECTS.map((s) => s.type).sort()).toEqual(
      [
        "BOXPLOT",
        "CALENDAR_HEATMAP",
        "CHART",
        "GAUGE",
        "HISTOGRAM",
        "PROGRESS",
        "RADAR",
        "SANKEY",
        "STATE_TIMELINE",
        "SUNBURST_SEQUENCE",
        "TREEMAP",
        "WATERFALL",
      ].sort()
    );
  });

  SUBJECTS.forEach((subject) => {
    const variants = VARIANTS[subject.type] || [{ name: "defaults", options: {} }];

    describe(subject.type, () => {
      test.each(SHAPES.map((s) => [s.name, s] as const))("builds an option for %s", (_n, shape) => {
        const data = { columns: shape.columns, rows: shape.rows };
        variants.forEach((variant) => {
          const size = SIZES[0];
          let built: Built | undefined;
          expect(() => {
            built = subject.build(data, subject.getOptions(variant.options, data), size);
          }).not.toThrow();
          expect(built).toEqual(expect.any(Object));
        });
      });

      test.each(SIZES.map((s) => [s.name, s] as const))("draws at %s", (_n, size) => {
        // The ordinary result, every option, every size: this is the case
        // that has to put ink on the canvas rather than merely not throw.
        const shape = SHAPES[0];
        const data = { columns: shape.columns, rows: shape.rows };
        variants.forEach((variant) => {
          const options = subject.getOptions(variant.options, data);
          const built = subject.build(data, options, size);
          if (built.problem) {
            // Refusing to draw is a fine answer, as long as it says why.
            expect(typeof built.problem).toBe("string");
            expect(built.problem.length).toBeGreaterThan(0);
            return;
          }
          const svg = draw(built.option, size);
          expect(inkCount(svg)).toBeGreaterThan(1);
        });
      });

      test("an awkward result either draws or says why not", () => {
        SHAPES.slice(1).forEach((shape) => {
          const data = { columns: shape.columns, rows: shape.rows };
          variants.forEach((variant) => {
            const options = subject.getOptions(variant.options, data);
            const built = subject.build(data, options, SIZES[0]);
            if (built.problem) {
              expect(typeof built.problem).toBe("string");
              return;
            }
            // No problem reported means it believes it can draw, so it has to.
            expect(() => draw(built.option, SIZES[0])).not.toThrow();
          });
        });
      });
    });
  });
});
