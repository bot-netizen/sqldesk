import { merge } from "lodash";
import ColorPalette from "@/visualizations/ColorPalette";
import { asValueFormat, fromNumeral } from "@/visualizations/shared/valueOptions";

const DEFAULT_OPTIONS = {
  timeInterval: "daily",
  mode: "diagonal",
  dateColumn: "date",
  stageColumn: "day_number",
  totalColumn: "total",
  valueColumn: "value",

  showTooltips: true,
  percentValues: true,

  timeColumnTitle: "Time",
  peopleColumnTitle: "Users",
  stageColumnTitle: "{{ @ }}",

  numberFormat: "0,0[.]00",
  percentFormat: "0.00%",
  noValuePlaceholder: "-",

  colors: {
    min: "#ffffff",
    max: ColorPalette["Dark Blue"],
    steps: 7,
  },
};

// Written as numeral format strings because that is what every saved cohort
// holds; `asValueFormat` below reads either shape.
const DEFAULT_NUMBER_FORMAT = fromNumeral(DEFAULT_OPTIONS.numberFormat)!;
const DEFAULT_PERCENT_FORMAT = fromNumeral(DEFAULT_OPTIONS.percentFormat)!;

export default function getOptions(options: any) {
  const result = merge({}, DEFAULT_OPTIONS, options);
  // Idempotent, because this runs on every render.
  result.numberFormat = asValueFormat(result.numberFormat, DEFAULT_NUMBER_FORMAT);
  result.percentFormat = asValueFormat(result.percentFormat, DEFAULT_PERCENT_FORMAT);
  return result;
}
