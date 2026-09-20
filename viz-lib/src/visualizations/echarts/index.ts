import * as echarts from "echarts/core";
import {
  BarChart,
  BoxplotChart,
  CustomChart,
  GaugeChart,
  HeatmapChart,
  LineChart,
  PieChart,
  SankeyChart,
  ScatterChart,
  SunburstChart,
} from "echarts/charts";
import {
  AriaComponent,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  MarkPointComponent,
  TitleComponent,
  TooltipComponent,
  VisualMapComponent,
} from "echarts/components";
import { UniversalTransition } from "echarts/features";
import { CanvasRenderer } from "echarts/renderers";

// Registered explicitly rather than importing the `echarts` barrel: the full
// build is 1.07MB minified and most of it is chart types we do not draw. Adding
// a series type here is a deliberate act with a measurable cost -- the audit
// measured each one against this list, and 0.4's additions (gauge, the three
// mark components, dataZoom, aria, title, universalTransition) come to 28.5KB
// gzipped.
//
// This lives above `chart/` because it is no longer only the chart
// visualization's: the sankey, sunburst, boxplot, gauge and progress
// visualizations draw with it too, and each needs its own series registered
// here.
//
// What is here is what more than one visualization needs, so it belongs in the
// chunk they share. A series only one visualization draws is registered by
// that visualization instead -- see radar, treemap, calendar and the drawn
// funnel -- so it travels in that visualization's own chunk and nobody else
// pays for it. `use` is incremental and idempotent, so registering late is
// fine as long as it happens before the chart is created, which a module-level
// call in a Renderer guarantees.
echarts.use([
  BarChart,
  BoxplotChart,
  // Error bars, and the point clouds beside a box, are drawn with renderItem:
  // ECharts ships no error-bar series, and a category axis snaps fractional
  // positions back to the category, so points cannot be offset any other way.
  CustomChart,
  GaugeChart,
  HeatmapChart,
  LineChart,
  PieChart,
  // A radar's spokes are a coordinate system of their own, so the series and
  // the component that lays it out are separate registrations.
  SankeyChart,
  ScatterChart,
  SunburstChart,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  // Heatmaps map a value onto a colour ramp, which is what visualMap does.
  VisualMapComponent,
  // Reference lines, threshold bands and min/max markers on any chart.
  MarkLineComponent,
  MarkAreaComponent,
  MarkPointComponent,
  // Zooming into, and windowing, long series.
  DataZoomComponent,
  // Labels drawn inside a chart, which a gauge's centre text needs.
  TitleComponent,
  // A text description of each chart for screen readers.
  AriaComponent,
  // Lets a series morph rather than cut when its shape changes on refresh.
  UniversalTransition,
  CanvasRenderer,
]);

export default echarts;
export { default as useEChart } from "./useEChart";
