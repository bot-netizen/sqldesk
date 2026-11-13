export interface SankeyDataType {
  columns: {
    name: string;
    friendly_name: string;
    type: "integer";
  }[];

  rows: {
    value: number;
    [name: string]: number | string | null;
  }[];
}

export default {
  type: "SANKEY",
  name: "Sankey",
  getOptions: (options: any) => ({
    // Every default is what a sankey did before it had the choice, so every
    // saved sankey draws as it did.
    showNodeValues: false,
    nodePercent: "none",
    flowLabels: false,
    colorScheme: "Classic",
    linkColor: "gradient",
    nodeColors: {},
    hiddenNodes: [],
    widthScale: "linear",
    nodeAlign: "justify",
    ...options,
  }),
  load: () => import(/* webpackChunkName: "viz-sankey" */ "./components"),

  defaultRows: 14,
};
