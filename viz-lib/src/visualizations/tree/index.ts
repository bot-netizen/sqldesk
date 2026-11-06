import getOptions from "./getOptions";

export default {
  type: "TREE",
  name: "Tree",
  getOptions,
  load: () => import(/* webpackChunkName: "viz-tree" */ "./components"),

  defaultColumns: 12,
  defaultRows: 18,
  minColumns: 6,
  minRows: 10,
};
