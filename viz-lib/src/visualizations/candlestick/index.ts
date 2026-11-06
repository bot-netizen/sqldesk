import getOptions from "./getOptions";

export default {
  type: "CANDLESTICK",
  name: "Candlestick",
  getOptions,
  load: () => import(/* webpackChunkName: "viz-candlestick" */ "./components"),

  defaultColumns: 12,
  defaultRows: 16,
  minColumns: 6,
  minRows: 8,
};
