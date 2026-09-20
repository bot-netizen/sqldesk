import getOptions from "./getOptions";
import Renderer from "./Renderer";
import Editor from "./Editor";

export default {
  type: "MAP",
  name: "Map (Markers)",
  getOptions,
  Renderer,
  Editor,

  defaultColumns: 12,
  defaultRows: 16,
  minColumns: 4,
};
