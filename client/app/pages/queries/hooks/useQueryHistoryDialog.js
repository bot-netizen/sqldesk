import { useCallback } from "react";
import QueryHistoryDialog from "@/components/queries/QueryHistoryDialog";
import useImmutableCallback from "@/lib/hooks/useImmutableCallback";

export default function useQueryHistoryDialog(query, canRestore, onChange, unsaved = false) {
  const handleChange = useImmutableCallback(onChange);

  return useCallback(() => {
    QueryHistoryDialog.showModal({ query, canRestore, unsaved }).onClose(handleChange);
  }, [query, canRestore, handleChange, unsaved]);
}
