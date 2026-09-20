export default {
  type: "BOXPLOT",
  name: "Boxplot (Deprecated)",
  isDeprecated: true,
  getOptions: (options: any) => ({
    ...options,
  }),
  load: () => import(/* webpackChunkName: "viz-box-plot" */ "./components"),

  defaultRows: 16,
  minRows: 10,
};
