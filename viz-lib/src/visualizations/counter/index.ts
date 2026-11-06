import { DEFAULT_VALUE_FORMAT, normalizeValueFormat } from "../shared/valueOptions";
import { DEFAULT_SPARKLINE, DEFAULT_COMPARISON } from "./stat";

const DEFAULT_OPTIONS = {
  counterLabel: "",
  counterColName: "counter",
  rowNumber: 1,
  targetRowNumber: 1,
  stringDecimal: 0,
  stringDecChar: ".",
  stringThouSep: ",",
  tooltipFormat: "0,0.000", // TODO: Show in editor
};

export function getOptions(options: any) {
  const saved = options || {};
  // A visualization being created starts from {}; one saved before 0.4 has
  // its classic options and no formatMode. Only the new one gets the shared
  // number format, so an existing counter reads exactly as it did.
  const isNew = Object.keys(saved).length === 0;
  return {
    ...DEFAULT_OPTIONS,
    ...saved,
    formatMode:
      saved.formatMode === "value" || saved.formatMode === "classic" ? saved.formatMode : isNew ? "value" : "classic",
    valueFormat: normalizeValueFormat(saved.valueFormat || DEFAULT_VALUE_FORMAT),
    sparkline: { ...DEFAULT_SPARKLINE, ...(saved.sparkline || {}) },
    comparison: { ...DEFAULT_COMPARISON, ...(saved.comparison || {}) },
    thresholds: saved.thresholds && typeof saved.thresholds === "object" ? saved.thresholds : { base: "", steps: [] },
  };
}

export default {
  type: "COUNTER",
  // Still COUNTER underneath, so every saved one keeps working; "Stat" is what
  // it has grown into -- a number with its trend.
  name: "Stat",
  getOptions,
  load: () => import(/* webpackChunkName: "viz-counter" */ "./components"),

  defaultColumns: 8,
  // Six, not ten. A stat is a number and a label; ten rows is 250 pixels of
  // mostly air, and a row of them pushed everything else below the fold.
  // Asked for directly after a dashboard built over MCP came out all strips
  // and empty tiles.
  defaultRows: 6,
};
