import getOptions from "./getOptions";

export default {
  type: "GAUGE",
  name: "Gauge",
  getOptions,
  load: () => import(/* webpackChunkName: "viz-gauge" */ "./components"),

  defaultColumns: 4,
  defaultRows: 12,
  minColumns: 2,
  minRows: 8,
};
