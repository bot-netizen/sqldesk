import getOptions from "./getOptions";

export default {
  type: "SUMMARY",
  name: "Summary",
  getOptions,
  load: () => import(/* webpackChunkName: "viz-summary" */ "./components"),
  // The top of a page: the whole width, and as tall as the words in it.
  defaultColumns: 24,
  defaultRows: 8,
  autoHeight: true,
};
