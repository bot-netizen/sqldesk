import _ from "lodash";
import { getDefaultFormatOptions, getColumnsOptions } from "@/visualizations/shared/columnUtils";

const DEFAULT_OPTIONS = {};

// The data argument defaults, because a visualization being created has
// no result yet and destructuring `undefined` throws before anything is
// drawn -- which takes the page down rather than showing an empty chart.
export default function getOptions(options: any, { columns }: any = {}) {
  options = { ...DEFAULT_OPTIONS, ...options };
  options.columns = _.map(getColumnsOptions(columns, options.columns, { alignContent: "left" }), (col) => ({
    ...getDefaultFormatOptions(col),
    ...col,
  }));
  return options;
}
