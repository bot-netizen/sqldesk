import getOptions from "./getOptions";

export default {
  type: "MAP",
  name: "Map (Markers)",
  getOptions,
  load: () => import(/* webpackChunkName: "viz-map" */ "./components"),

  defaultColumns: 12,
  defaultRows: 16,
  minColumns: 4,
};
