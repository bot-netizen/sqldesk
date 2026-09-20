import getOptions from "./getOptions";

export default {
  type: "HISTOGRAM",
  name: "Histogram",
  getOptions,
  load: () => import(/* webpackChunkName: "viz-histogram" */ "./components"),

  defaultColumns: 12,
  defaultRows: 16,
  minColumns: 4,
  minRows: 8,
};
