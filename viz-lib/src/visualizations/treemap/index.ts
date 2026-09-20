import getOptions from "./getOptions";

export default {
  type: "TREEMAP",
  name: "Treemap",
  getOptions,
  load: () => import(/* webpackChunkName: "viz-treemap" */ "./components"),

  defaultColumns: 12,
  defaultRows: 16,
  minColumns: 4,
  minRows: 8,
};
