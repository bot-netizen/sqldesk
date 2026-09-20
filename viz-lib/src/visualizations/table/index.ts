import getOptions from "./getOptions";
import Renderer from "./Renderer";
import Editor from "./Editor";

export default {
  type: "TABLE",
  name: "Table",
  getOptions,
  Renderer,
  Editor,

  autoHeight: true,
  defaultRows: 28,
  defaultColumns: 12,
  minColumns: 4,
};
