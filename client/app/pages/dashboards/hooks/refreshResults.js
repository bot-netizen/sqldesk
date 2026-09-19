import { isFunction, map } from "lodash";

function resultIdOf(widget) {
  const result = widget.getQueryResult();
  return result && isFunction(result.getId) ? result.getId() : null;
}

/**
 * The ids of the results the widgets show now, to compare after a Refresh:
 * the same ids afterwards mean every result was under a minute old and was
 * reused rather than run again.
 */
export function shownResultIds(widgets) {
  return map(widgets, resultIdOf);
}

export function nothingWasRun(before, widgets) {
  const after = shownResultIds(widgets);
  return before.some((id) => id !== null) && before.every((id, i) => id === after[i]);
}
