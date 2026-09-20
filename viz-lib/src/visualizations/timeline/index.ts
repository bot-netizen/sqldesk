import getOptions from "./getOptions";

export default {
  type: "STATE_TIMELINE",
  name: "State Timeline",
  getOptions,
  load: () => import(/* webpackChunkName: "viz-timeline" */ "./components"),

  defaultColumns: 24,
  defaultRows: 12,
  minColumns: 8,
  minRows: 6,
};
