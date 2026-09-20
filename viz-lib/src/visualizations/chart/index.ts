import getOptions from "./getOptions";
import Renderer from "./Renderer";
import Editor from "./Editor";

export default {
  type: "CHART",
  name: "Chart",
  isDefault: true,
  getOptions,
  Renderer,
  Editor,

  defaultColumns: 12,
  defaultRows: 16,
  minColumns: 2,
  minRows: 10,
};
