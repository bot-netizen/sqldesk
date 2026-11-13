import { isArray, isString } from "lodash";
import { starterTemplate } from "./template";

export const LAYOUTS = ["sentence", "bullets", "status"] as const;

// The data argument defaults, because a visualization being created has no
// result yet and destructuring `undefined` throws before anything is drawn.
export default function getOptions(options: any, { columns }: any = {}) {
  const saved = options || {};
  return {
    ...saved,
    // A new summary opens on a sentence that works, made from its own result,
    // rather than an empty box. One saved empty on purpose stays empty.
    template: isString(saved.template) ? saved.template : starterTemplate(columns || []),
    layout: (LAYOUTS as readonly string[]).includes(saved.layout) ? saved.layout : "sentence",
    rules: isArray(saved.rules) ? saved.rules.filter((rule: any) => rule && rule.column) : [],
  };
}
