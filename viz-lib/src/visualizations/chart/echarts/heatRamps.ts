// Heatmap colour ramps.
//
// The heatmap editor offers the names Plotly shipped, and existing saved
// visualizations hold those names in their options. ECharts has no equivalent,
// so each scale is resampled here at nine evenly spaced stops and handed to
// visualMap, which spreads an array evenly across the value range.
//
// Values derived from the named colorscales in plotly.js (MIT licence),
// resampled rather than copied so the array suits visualMap directly.

/** The ramp Plotly used when no scheme was chosen. */
export const DEFAULT_HEAT_RAMP = [
  "#356aff",
  "#4a7aff",
  "#5d87ff",
  "#7398ff",
  "#fb8c8c",
  "#ec6463",
  "#ec4949",
  "#e92827",
];

export const HEAT_RAMPS: { [name: string]: string[] } = {
  Blackbody: ["#000000", "#900000", "#e63400", "#e6b800", "#eee155", "#f9f4bf", "#eff6ff", "#c8dfff", "#a0c8ff"],
  Bluered: ["#0000ff", "#2000df", "#4000bf", "#60009f", "#800080", "#9f0060", "#bf0040", "#df0020", "#ff0000"],
  Blues: ["#050aac", "#121cb2", "#1e2eb9", "#2d43c7", "#4664f5", "#5e7cf6", "#7d97f3", "#adb9e7", "#dcdcdc"],
  Earth: ["#000082", "#0abc91", "#58d72b", "#cee431", "#af9623", "#805223", "#ab8b6c", "#d5c5b6", "#ffffff"],
  Electric: ["#000000", "#190053", "#420064", "#6f0064", "#8c2d32", "#a96800", "#d5ad00", "#efdb52", "#fffadc"],
  Greens: ["#00441b", "#006d2c", "#238b45", "#41ab5d", "#74c476", "#a1d99b", "#c7e9c0", "#e5f5e0", "#f7fcf5"],
  Greys: ["#000000", "#202020", "#404040", "#606060", "#808080", "#9f9f9f", "#bfbfbf", "#dfdfdf", "#ffffff"],
  Hot: ["#000000", "#600000", "#c00000", "#ec3500", "#f78c00", "#ffd510", "#ffe360", "#fff1af", "#ffffff"],
  Jet: ["#000083", "#003caa", "#039ed5", "#05ffff", "#82ff80", "#ffff00", "#fd8000", "#fa0000", "#800000"],
  Picnic: ["#0000ff", "#40a6ff", "#80ccff", "#bfccff", "#ffffff", "#ffbfff", "#ff80e6", "#ff6680", "#ff0000"],
  Portland: ["#0c3383", "#0b5e9f", "#0a88ba", "#7eae79", "#f2d338", "#f2b138", "#f28f38", "#e6572b", "#d91e1e"],
  Rainbow: ["#96005a", "#0000c8", "#0019ff", "#0098ff", "#2cff96", "#97ff00", "#ffea00", "#ff6f00", "#ff0000"],
  RdBu: ["#050aac", "#2937c7", "#4d65e2", "#7892ee", "#bebebe", "#dfa479", "#dd7a50", "#c84236", "#b20a1c"],
  Reds: ["#dcdcdc", "#ecccb5", "#f5ba90", "#f5a470", "#ea875c", "#dc684c", "#ce493c", "#c0292c", "#b20a1c"],
  Viridis: ["#440154", "#472d7b", "#3b528b", "#2c728e", "#21918c", "#28ad80", "#5dc863", "#abdc31", "#fde725"],
  YlGnBu: ["#081d58", "#253494", "#225ea8", "#1d91c0", "#41b6c4", "#7fcdbb", "#c7e9b4", "#edf8d9", "#ffffd9"],
  YlOrRd: ["#800026", "#bd0026", "#e31a1c", "#fc4e2a", "#fd8d3c", "#feb24c", "#fed976", "#ffeda0", "#ffffcc"],
};
