import getOptions from "./getOptions";

export default {
  type: "CHOROPLETH",
  name: "Map (Choropleth)",
  getOptions,
  load: () => import(/* webpackChunkName: "viz-choropleth" */ "./components"),

  defaultColumns: 12,
  defaultRows: 16,
  minColumns: 4,
};
