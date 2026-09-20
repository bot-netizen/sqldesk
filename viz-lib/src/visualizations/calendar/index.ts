import getOptions from "./getOptions";

export default {
  type: "CALENDAR_HEATMAP",
  name: "Calendar Heatmap",
  getOptions,
  load: () => import(/* webpackChunkName: "viz-calendar" */ "./components"),

  defaultColumns: 24,
  defaultRows: 12,
  minColumns: 8,
  minRows: 8,
};
