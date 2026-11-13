import createTabbedEditor from "@/components/visualizations/editor/createTabbedEditor";

import TextSettings from "./TextSettings";
import RulesSettings from "./RulesSettings";
import "../render.less";

export default createTabbedEditor([
  { key: "Text", title: "Text", component: TextSettings },
  { key: "Colours", title: "Colours", component: RulesSettings },
]);
