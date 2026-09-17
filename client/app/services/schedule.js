import { isArray, intersection } from "lodash";
import { clientConfig } from "@/services/auth";
import { policy } from "@/services/policy";

/**
 * The refresh intervals this installation offers, narrowed to what the policy
 * allows.
 *
 * Used for query schedules and for dashboard schedules alike: a dashboard's
 * schedule runs the queries behind its widgets, so it is the query intervals
 * that apply, not `dashboardRefreshIntervals` -- those govern how often an open
 * browser tab re-polls, which is a different thing entirely.
 */
export function getRefreshOptions() {
  const intervals = clientConfig.queryRefreshIntervals;
  const allowedIntervals = policy.getQueryRefreshIntervals();
  return isArray(allowedIntervals) ? intersection(intervals, allowedIntervals) : intervals;
}

export default { getRefreshOptions };
