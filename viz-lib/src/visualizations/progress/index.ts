import Renderer from "./Renderer";
import Editor from "./Editor";
import getOptions from "./getOptions";

export default {
  type: "PROGRESS",
  name: "Progress Bars",
  getOptions,
  Renderer,
  Editor,

  defaultColumns: 3,
  defaultRows: 6,
  minRows: 3,
};
