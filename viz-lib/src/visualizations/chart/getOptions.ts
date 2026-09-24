import { merge } from "lodash";
import { visualizationsSettings } from "@/visualizations/visualizationsSettings";
import { DEFAULT_COLOR_SCHEME, resolveColorScheme } from "@/visualizations/ColorPalette";
import { asValueFormat, fromNumeral } from "@/visualizations/shared/valueOptions";
import { normalizeSeriesTypes } from "./echarts/utils";

const DEFAULT_OPTIONS = {
  globalSeriesType: "column",
  sortX: true,
  legend: { enabled: true, placement: "auto", traceorder: "normal" },
  xAxis: { type: "-", labels: { enabled: true } },
  yAxis: [{ type: "linear" }, { type: "linear", opposite: true }],
  alignYAxesAtZero: false,
  error_y: { type: "data", visible: true },
  series: { stacking: null, error_y: { type: "data", visible: true } },
  seriesOptions: {},
  valuesOptions: {},
  columnMapping: {},
  direction: { type: "counterclockwise" },
  sizemode: "diameter",
  coefficient: 1,
  piesort: true,
  // "pie" or "rose" -- a Nightingale rose gives every slice the same angle and
  // puts the value in the radius. Pies saved before this stay pies.
  pieStyle: "pie",
  color_scheme: DEFAULT_COLOR_SCHEME,
  lineShape: "linear",

  // showDataLabels: false, // depends on chart type
  numberFormat: "0,0[.]00000",
  percentFormat: "0[.]00%",
  // dateTimeFormat: 'DD/MM/YYYY HH:mm', // will be set from visualizationsSettings
  textFormat: "", // default: combination of {{ @@yPercent }} ({{ @@y }} ± {{ @@yError }})

  enableLink: false,
  linkOpenNewTab: true,
  linkFormat: "", // template like a textFormat

  missingValuesAsZero: true,

  // 0.4: goal lines, bands, a rolling window and zoom. All off by default.
  referenceLines: [],
  referenceBands: [],
  window: { mode: "all", points: 50, minutes: 60 },
  zoom: "none",
};

// Written as numeral format strings because that is what every saved chart
// holds; `asValueFormat` below reads either shape.
const DEFAULT_NUMBER_FORMAT = fromNumeral(DEFAULT_OPTIONS.numberFormat)!;
const DEFAULT_PERCENT_FORMAT = fromNumeral(DEFAULT_OPTIONS.percentFormat)!;

export default function getOptions(options: any) {
  // Options can arrive as null through the API, and the series type is read
  // below before `merge` has had a chance to supply a default.
  options = options || {};
  const result = merge(
    {},
    DEFAULT_OPTIONS,
    {
      showDataLabels: options.globalSeriesType === "pie",
      dateTimeFormat: visualizationsSettings.dateTimeFormat,
    },
    options
  );

  // Backward compatibility
  if (["normal", "percent"].indexOf(result.series.stacking) >= 0) {
    result.series.percentValues = result.series.stacking === "percent";
    result.series.stacking = "stack";
  }

  // Charts saved before the rename store color_scheme "Redash"
  result.color_scheme = resolveColorScheme(result.color_scheme);

  // A saved chart holds numeral format strings; the editor writes the shared
  // format. Idempotent, because this runs on every render.
  result.numberFormat = asValueFormat(result.numberFormat, DEFAULT_NUMBER_FORMAT);
  result.percentFormat = asValueFormat(result.percentFormat, DEFAULT_PERCENT_FORMAT);

  // A saved chart can name a type the renderer no longer has -- "custom" most
  // of all, which was Plotly-only. Correct it here rather than at draw time, so
  // the editor shows what will actually be rendered.
  return normalizeSeriesTypes(result);
}
