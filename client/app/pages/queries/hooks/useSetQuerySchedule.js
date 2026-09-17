import { isArray, intersection } from "lodash";
import { useCallback, useMemo } from "react";
import { clientConfig } from "@/services/auth";
import { policy } from "@/services/policy";
import recordEvent from "@/services/recordEvent";
import useUpdateQuery from "./useUpdateQuery";
import useQueryFlags from "./useQueryFlags";

// The intervals this installation offers, narrowed to what the policy allows.
// Kept here rather than read straight from clientConfig at the point of use,
// so the menu and anything else offering intervals narrow them the same way.
export function getRefreshOptions() {
  const intervals = clientConfig.queryRefreshIntervals;
  const allowedIntervals = policy.getQueryRefreshIntervals();
  return isArray(allowedIntervals) ? intersection(intervals, allowedIntervals) : intervals;
}

// Setting an interval straight from the header menu, without opening the
// dialog. Anything needing a time of day, a weekday or an end date still goes
// through the dialog.
export default function useSetQuerySchedule(query, onChange) {
  // Flags that depend on the data source are not used: scheduling does not
  // depend on one.
  const queryFlags = useQueryFlags(query);
  const updateQuery = useUpdateQuery(query, onChange);
  const refreshOptions = useMemo(getRefreshOptions, []);

  const setInterval = useCallback(
    (seconds) => {
      if (!queryFlags.canEdit || !queryFlags.canSchedule) {
        return;
      }
      recordEvent("edit_schedule", "query", query.id);
      // Never is null, not a schedule whose interval is null: that is what has
      // always been stored for it and the two are not interchangeable
      // downstream. Everything else is cleared explicitly -- a query that used
      // to run weekly at 09:00 keeps a time and a weekday otherwise, and a
      // crontab expression would go on winning, so picking an interval would
      // appear to do nothing.
      const schedule = seconds
        ? {
            interval: seconds,
            time: null,
            day_of_week: null,
            until: (query.schedule && query.schedule.until) || null,
            cron: null,
          }
        : null;
      updateQuery({ schedule });
    },
    [query.id, query.schedule, queryFlags.canEdit, queryFlags.canSchedule, updateQuery]
  );

  // A crontab schedule replaces the interval rather than sitting beside it:
  // should_schedule_next reads the expression and ignores the rest, and leaving
  // a stale interval behind would only mislead anyone reading the record.
  const setCron = useCallback(
    (cron) => {
      if (!queryFlags.canEdit || !queryFlags.canSchedule) {
        return;
      }
      recordEvent("edit_schedule", "query", query.id);
      updateQuery({
        schedule: {
          interval: null,
          time: null,
          day_of_week: null,
          until: (query.schedule && query.schedule.until) || null,
          cron,
        },
      });
    },
    [query.id, query.schedule, queryFlags.canEdit, queryFlags.canSchedule, updateQuery]
  );

  return { refreshOptions, setInterval, setCron };
}
