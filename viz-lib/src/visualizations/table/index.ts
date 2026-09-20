import getOptions from "./getOptions";

export default {
  type: "TABLE",
  name: "Table",
  getOptions,
  load: () => import(/* webpackChunkName: "viz-table" */ "./components"),

  autoHeight: true,
  defaultRows: 28,
  defaultColumns: 12,
  minColumns: 4,
};
