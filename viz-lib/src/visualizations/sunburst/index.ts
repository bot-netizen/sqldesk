export default {
  type: "SUNBURST_SEQUENCE",
  name: "Sunburst Sequence",
  getOptions: (options: any) => ({
    ...options,
  }),
  load: () => import(/* webpackChunkName: "viz-sunburst" */ "./components"),

  defaultRows: 14,
};
