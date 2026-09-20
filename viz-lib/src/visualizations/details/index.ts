import getOptions from "./getOptions";

export default {
  type: "DETAILS",
  name: "Details View",
  getOptions,
  load: () => import(/* webpackChunkName: "viz-details" */ "./components"),
  defaultColumns: 8,
  defaultRows: 4,
};
