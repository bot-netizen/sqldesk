import getOptions from "./getOptions";

export default {
  type: "STREAMGRAPH",
  name: "Streamgraph",
  getOptions,
  load: () => import(/* webpackChunkName: "viz-streamgraph" */ "./components"),

  defaultColumns: 12,
  defaultRows: 16,
  minColumns: 6,
  minRows: 8,
};
