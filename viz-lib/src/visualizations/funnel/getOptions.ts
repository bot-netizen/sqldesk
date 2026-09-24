import { isFinite, map, merge, includes } from "lodash";
import { asValueFormat, fromNumeral } from "@/visualizations/shared/valueOptions";

const DEFAULT_OPTIONS = {
  // "bars" is the table with a bar in each row, which is what a funnel has
  // always looked like here; "funnel" is the drawn shape.
  shape: "bars",
  stepCol: { colName: null, displayAs: "Steps" },
  valueCol: { colName: null, displayAs: "Value" },
  autoSort: true,
  sortKeyCol: { colName: null, reverse: false },
  itemsLimit: 100,
  percentValuesRange: { min: 0.01, max: 1000.0 },
  numberFormat: "0,0[.]00",
  percentFormat: "0[.]00%",
};

// The two defaults above as they are actually used. They are still written as
// numeral format strings because that is what every saved funnel holds, and
// `asValueFormat` reads either shape.
const DEFAULT_NUMBER_FORMAT = fromNumeral(DEFAULT_OPTIONS.numberFormat)!;
const DEFAULT_PERCENT_FORMAT = fromNumeral(DEFAULT_OPTIONS.percentFormat)!;

// The data argument defaults, because a visualization being created has
// no result yet and destructuring `undefined` throws before anything is
// drawn -- which takes the page down rather than showing an empty chart.
export default function getOptions(options: any, { columns }: any = {}) {
  options = merge({}, DEFAULT_OPTIONS, options);

  // Validate
  const availableColumns = map(columns, (c) => c.name);
  if (!includes(availableColumns, options.stepCol.colName)) {
    options.stepCol.colName = null;
  }
  if (!includes(availableColumns, options.valueCol.colName)) {
    options.valueCol.colName = null;
  }
  if (!includes(availableColumns, options.sortKeyCol.colName)) {
    options.sortKeyCol.colName = null;
  }

  if (!isFinite(options.itemsLimit)) {
    options.itemsLimit = DEFAULT_OPTIONS.itemsLimit;
  }
  if (options.itemsLimit < 2) {
    options.itemsLimit = 2;
  }

  options.shape = options.shape === "funnel" ? "funnel" : "bars";

  // A saved funnel holds numeral format strings; the editor writes the shared
  // format. Idempotent, because this runs on every render.
  options.numberFormat = asValueFormat(options.numberFormat, DEFAULT_NUMBER_FORMAT);
  options.percentFormat = asValueFormat(options.percentFormat, DEFAULT_PERCENT_FORMAT);

  if (options.autoSort) {
    options.sortKeyCol.colName = options.valueCol.colName;
    options.sortKeyCol.reverse = true;
  }

  return options;
}
