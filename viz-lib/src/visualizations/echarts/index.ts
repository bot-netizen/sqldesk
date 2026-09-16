import * as echarts from "echarts/core";
import {
  BarChart,
  BoxplotChart,
  CustomChart,
  HeatmapChart,
  LineChart,
  PieChart,
  SankeyChart,
  ScatterChart,
  SunburstChart,
} from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent, VisualMapComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

// Registered explicitly rather than importing the `echarts` barrel: the full
// build is 1.07MB minified and most of it is chart types we do not draw. Adding
// a series type here is a deliberate act with a measurable cost.
//
// This lives above `chart/` because it is no longer only the chart
// visualization's: the sankey, sunburst and boxplot visualizations draw with it
// too, and each needs its own series registered here.
echarts.use([
  BarChart,
  BoxplotChart,
  // Error bars, and the point clouds beside a box, are drawn with renderItem:
  // ECharts ships no error-bar series, and a category axis snaps fractional
  // positions back to the category, so points cannot be offset any other way.
  CustomChart,
  HeatmapChart,
  LineChart,
  PieChart,
  SankeyChart,
  ScatterChart,
  SunburstChart,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  // Heatmaps map a value onto a colour ramp, which is what visualMap does.
  VisualMapComponent,
  CanvasRenderer,
]);

export default echarts;
export { default as useEChart } from "./useEChart";
