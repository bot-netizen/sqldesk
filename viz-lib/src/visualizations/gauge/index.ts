import Renderer from "./Renderer";
import Editor from "./Editor";
import getOptions from "./getOptions";

export default {
  type: "GAUGE",
  name: "Gauge",
  getOptions,
  Renderer,
  Editor,

  defaultColumns: 4,
  defaultRows: 12,
  minColumns: 2,
  minRows: 8,
};
