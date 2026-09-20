import getOptions from "./getOptions";

export default {
  type: "COHORT",
  name: "Cohort",
  getOptions,
  load: () => import(/* webpackChunkName: "viz-cohort" */ "./components"),

  autoHeight: true,
  defaultRows: 16,
};
