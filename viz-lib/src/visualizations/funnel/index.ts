import getOptions from "./getOptions";

export default {
  type: "FUNNEL",
  name: "Funnel",
  getOptions,
  load: () => import(/* webpackChunkName: "viz-funnel" */ "./components"),

  defaultRows: 20,
};
