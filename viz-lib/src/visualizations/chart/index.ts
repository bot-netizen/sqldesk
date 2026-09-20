import getOptions from "./getOptions";

export default {
  type: "CHART",
  name: "Chart",
  isDefault: true,
  getOptions,
  load: () => import(/* webpackChunkName: "viz-chart" */ "./components"),

  defaultColumns: 12,
  defaultRows: 16,
  minColumns: 2,
  minRows: 10,
};
