import getOptions from "./getOptions";

export default {
  type: "WATERFALL",
  name: "Waterfall",
  getOptions,
  load: () => import(/* webpackChunkName: "viz-waterfall" */ "./components"),

  defaultColumns: 12,
  defaultRows: 16,
  minColumns: 4,
  minRows: 8,
};
