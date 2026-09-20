import getOptions from "./getOptions";

export default {
  type: "RADAR",
  name: "Radar",
  getOptions,
  load: () => import(/* webpackChunkName: "viz-radar" */ "./components"),

  defaultColumns: 8,
  defaultRows: 16,
  minColumns: 4,
  minRows: 10,
};
