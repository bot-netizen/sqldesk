import { useCallback } from "react";
import CronScheduleDialog from "@/components/queries/CronScheduleDialog";
import recordEvent from "@/services/recordEvent";
import useUpdateQuery from "./useUpdateQuery";
import useQueryFlags from "./useQueryFlags";
import useSetQuerySchedule from "./useSetQuerySchedule";

// Anything beyond the handful of intervals in the refresh menu is written as a
// crontab expression. It says "09:00 on weekdays" exactly, which the interval
// plus time-of-day plus weekday form it replaced could only approximate, and it
// needs one field instead of four.
export default function useEditCronDialog(query, onChange) {
  // Matching what was here before: flags that depend on the data source are not
  // used, because scheduling does not depend on one.
  const queryFlags = useQueryFlags(query);
  const { setCron } = useSetQuerySchedule(query, onChange);

  return useCallback(() => {
    if (!queryFlags.canEdit || !queryFlags.canSchedule) {
      return;
    }

    CronScheduleDialog.showModal({
      cron: (query.schedule && query.schedule.cron) || "",
    }).onClose((cron) => {
      setCron(cron);
    });
  }, [query.schedule, queryFlags.canEdit, queryFlags.canSchedule, setCron]);
}
