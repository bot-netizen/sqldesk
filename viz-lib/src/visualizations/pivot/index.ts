import { merge } from "lodash";

const DEFAULT_OPTIONS = {
  controls: {
    enabled: false, // `false` means "show controls" o_O
  },
  rendererOptions: {
    table: {
      colTotals: true,
      rowTotals: true,
    },
  },
};

export default {
  type: "PIVOT",
  name: "Pivot Table",
  getOptions: (options: any) => merge({}, DEFAULT_OPTIONS, options),
  load: () => import(/* webpackChunkName: "viz-pivot" */ "./components"),

  defaultRows: 20,
  defaultColumns: 12,
  minColumns: 4,
};
