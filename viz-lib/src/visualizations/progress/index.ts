import getOptions from "./getOptions";

export default {
  type: "PROGRESS",
  name: "Progress Bars",
  getOptions,
  load: () => import(/* webpackChunkName: "viz-progress" */ "./components"),

  defaultColumns: 6,
  defaultRows: 12,
  minRows: 6,
};
