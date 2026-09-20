import Renderer from "./Renderer";
import Editor from "./Editor";

export default {
  type: "BOXPLOT",
  name: "Boxplot (Deprecated)",
  isDeprecated: true,
  getOptions: (options: any) => ({
    ...options,
  }),
  Renderer,
  Editor,

  defaultRows: 16,
  minRows: 10,
};
