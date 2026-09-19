/**
 * How old a result an auto-refresh tick accepts instead of running the query.
 *
 * Other open tabs' results should do -- that is the point -- but this tab's
 * own last result is just under one interval old when its timer fires again,
 * so accepting a whole interval reused it and the dashboard refreshed every
 * other tick at best. Half the interval still lets tabs share a run.
 */
export function autoRefreshMaxAge(refreshRate) {
  return Math.floor(refreshRate / 2);
}
