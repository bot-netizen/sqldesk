import getOptions from "./getOptions";

export default {
  type: "NETWORK",
  name: "Network",
  getOptions,
  load: () => import(/* webpackChunkName: "viz-network" */ "./components"),

  defaultColumns: 12,
  defaultRows: 18,
  minColumns: 6,
  minRows: 10,
};
