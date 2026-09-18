import createTabbedEditor from "@/components/visualizations/editor/createTabbedEditor";

import GeneralSettings from "./GeneralSettings";
import FormatSettings from "./FormatSettings";
import TrendSettings from "./TrendSettings";
import ColourSettings from "./ColourSettings";

export default createTabbedEditor([
  { key: "General", title: "General", component: GeneralSettings },
  { key: "Trend", title: "Trend", component: TrendSettings },
  { key: "Format", title: "Format", component: FormatSettings },
  { key: "Colours", title: "Colours", component: ColourSettings },
]);
