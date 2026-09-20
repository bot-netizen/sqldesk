import { merge } from "lodash";

const DEFAULT_OPTIONS = {
  column: "",
  frequenciesColumn: "",
  wordLengthLimit: { min: null, max: null },
  wordCountLimit: { min: null, max: null },
};

export default {
  type: "WORD_CLOUD",
  name: "Word Cloud",
  getOptions: (options: any) => merge({}, DEFAULT_OPTIONS, options),
  load: () => import(/* webpackChunkName: "viz-word-cloud" */ "./components"),

  defaultRows: 16,
};
