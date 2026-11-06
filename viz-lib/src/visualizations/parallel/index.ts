import getOptions from "./getOptions";

export default {
  type: "PARALLEL",
  name: "Parallel coordinates",
  getOptions,
  load: () => import(/* webpackChunkName: "viz-parallel" */ "./components"),

  defaultColumns: 12,
  defaultRows: 16,
  minColumns: 6,
  minRows: 8,
};
