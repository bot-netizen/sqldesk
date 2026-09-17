import { useCallback, useMemo } from "react";
import CronScheduleDialog from "@/components/queries/CronScheduleDialog";
import { getRefreshOptions } from "@/services/schedule";

/**
 * A dashboard's refresh schedule.
 *
 * Distinct from the refresh rate beside it in the header: that is a timer in
 * this browser tab, re-polling while somebody watches, and it is forgotten when
 * the tab closes. This is stored on the dashboard, and the server refreshes the
 * queries behind its widgets whether anyone is looking or not -- which is what
 * makes a dashboard ready before people arrive rather than after.
 */
export default function useDashboardSchedule(dashboard, updateDashboard) {
  const refreshOptions = useMemo(getRefreshOptions, []);

  const setInterval = useCallback(
    (seconds) => {
      // null clears the schedule, matching how a query stores "never". Picking
      // an interval clears any expression, or the expression would go on
      // winning and the menu would appear to do nothing.
      updateDashboard({ schedule: seconds ? { interval: seconds, cron: null } : null }, false);
    },
    [updateDashboard]
  );

  const editCron = useCallback(() => {
    CronScheduleDialog.showModal({
      cron: (dashboard.schedule && dashboard.schedule.cron) || "",
    }).onClose((cron) => {
      updateDashboard({ schedule: { interval: null, cron } }, false);
    });
  }, [dashboard.schedule, updateDashboard]);

  return { refreshOptions, setInterval, editCron };
}
