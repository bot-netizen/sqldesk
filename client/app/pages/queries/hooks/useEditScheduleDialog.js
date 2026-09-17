import { useCallback } from "react";
import ScheduleDialog from "@/components/queries/ScheduleDialog";
import useUpdateQuery from "./useUpdateQuery";
import useQueryFlags from "./useQueryFlags";
import { getRefreshOptions } from "./useSetQuerySchedule";
import recordEvent from "@/services/recordEvent";

export default function useEditScheduleDialog(query, onChange) {
  // We won't use flags that depend on data source
  const queryFlags = useQueryFlags(query);

  const updateQuery = useUpdateQuery(query, onChange);

  return useCallback(() => {
    if (!queryFlags.canEdit || !queryFlags.canSchedule) {
      return;
    }

    ScheduleDialog.showModal({
      schedule: query.schedule,
      refreshOptions: getRefreshOptions(),
    }).onClose((schedule) => {
      recordEvent("edit_schedule", "query", query.id);
      updateQuery({ schedule });
    });
  }, [query.id, query.schedule, queryFlags.canEdit, queryFlags.canSchedule, updateQuery]);
}
