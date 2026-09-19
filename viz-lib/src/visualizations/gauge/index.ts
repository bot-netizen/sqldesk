import Renderer from "./Renderer";
import Editor from "./Editor";
import getOptions from "./getOptions";

export default {
  type: "GAUGE",
  name: "Gauge",
  getOptions,
  Renderer,
  Editor,

  defaultColumns: 2,
  defaultRows: 6,
  minColumns: 1,
  minRows: 4,
};
