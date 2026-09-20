import Renderer from "./Renderer";
import Editor from "./Editor";
import getOptions from "./getOptions";

export default {
  type: "STATUS_GRID",
  name: "Status Grid",
  getOptions,
  Renderer,
  Editor,

  defaultColumns: 12,
  defaultRows: 10,
  minRows: 4,
};
