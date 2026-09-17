import { isArray, intersection } from "lodash";
import { useCallback, useMemo } from "react";
import { clientConfig } from "@/services/auth";
import { policy } from "@/services/policy";
import { scheduleForInterval } from "@/components/queries/ScheduleDialog";
import recordEvent from "@/services/recordEvent";
import useUpdateQuery from "./useUpdateQuery";
import useQueryFlags from "./useQueryFlags";

// The intervals this installation offers, narrowed to what the policy allows.
// Shared with useEditScheduleDialog so the header menu and the dialog can never
// offer different sets.
export function getRefreshOptions() {
  const intervals = clientConfig.queryRefreshIntervals;
  const allowedIntervals = policy.getQueryRefreshIntervals();
  return isArray(allowedIntervals) ? intersection(intervals, allowedIntervals) : intervals;
}

// Setting an interval straight from the header menu, without opening the
// dialog. Anything needing a time of day, a weekday or an end date still goes
// through the dialog.
export default function useSetQuerySchedule(query, onChange) {
  // Matching useEditScheduleDialog: flags that depend on the data source are
  // not used here.
  const queryFlags = useQueryFlags(query);
  const updateQuery = useUpdateQuery(query, onChange);
  const refreshOptions = useMemo(getRefreshOptions, []);

  const setInterval = useCallback(
    (seconds) => {
      if (!queryFlags.canEdit || !queryFlags.canSchedule) {
        return;
      }
      recordEvent("edit_schedule", "query", query.id);
      // The dialog closes with null for "never" rather than with a schedule
      // whose interval is null, and the two are not interchangeable downstream.
      updateQuery({ schedule: seconds ? scheduleForInterval(query.schedule, seconds) : null });
    },
    [query.id, query.schedule, queryFlags.canEdit, queryFlags.canSchedule, updateQuery]
  );

  return { refreshOptions, setInterval };
}
