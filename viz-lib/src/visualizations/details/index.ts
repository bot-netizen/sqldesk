import getOptions from "./getOptions";

export default {
  type: "DETAILS",
  name: "Details View",
  getOptions,
  load: () => import(/* webpackChunkName: "viz-details" */ "./components"),
  defaultColumns: 8,
  // One row per field and a pager under them: a card that sizes itself, like
  // a table. Four rows was a hundred pixels, which the widget's header and
  // footer used up -- the card was a 7px strip on the demo dashboard.
  autoHeight: true,
  defaultRows: 16,
};
