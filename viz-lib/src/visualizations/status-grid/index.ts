import getOptions from "./getOptions";

export default {
  type: "STATUS_GRID",
  name: "Status Grid",
  getOptions,
  load: () => import(/* webpackChunkName: "viz-status-grid" */ "./components"),

  defaultColumns: 12,
  defaultRows: 10,
  minRows: 4,
};
