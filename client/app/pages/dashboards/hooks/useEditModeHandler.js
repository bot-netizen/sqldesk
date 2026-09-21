import { find, has, isEmpty, isMatch, map, pickBy } from "lodash";
import { useCallback, useEffect, useRef, useState } from "react";
import location from "@/services/location";
import notification from "@/services/notification";

export const DashboardStatusEnum = {
  SAVED: "saved",
  UNSAVED: "unsaved",
  SAVING: "saving",
  SAVING_FAILED: "saving_failed",
};

function getChangedPositions(widgets, nextPositions = {}) {
  return pickBy(nextPositions, (nextPos, widgetId) => {
    const widget = find(widgets, { id: Number(widgetId) });
    // Deleted while the layout was being edited: there is nothing left to
    // move, and reading a position off it would throw.
    if (!widget) {
      return false;
    }
    return !isMatch(widget.options.position, nextPos);
  });
}

/**
 * Editing a dashboard's layout, and saving it when asked to.
 *
 * Dragging and resizing used to write to the server about two seconds later,
 * every time, so a dashboard was changed by opening it and moving something --
 * whether or not Done Editing was ever pressed, and with no way back. Now the
 * arrangement is held here until it is saved on purpose, and Discard throws it
 * away.
 *
 * Nothing is written until `saveDashboardLayout` is called, so a caller that
 * lets someone leave the page with `hasUnsavedChanges` set has lost their
 * work -- see useUnsavedChangesAlert, which is what stops that.
 */
export default function useEditModeHandler(canEditDashboard, widgets) {
  const [editingLayout, setEditingLayout] = useState(canEditDashboard && has(location.search, "edit"));
  const [dashboardStatus, setDashboardStatus] = useState(DashboardStatusEnum.SAVED);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);

  // The arrangement on screen, which is not the stored one until it is saved.
  // A ref because the grid reports it on every frame of a drag, and rendering
  // the page again on each of those would make dragging stutter.
  const pendingPositions = useRef({});

  // Bumped to make the grid rebuild itself from the stored positions. That is
  // all discarding takes, because the widgets themselves were never changed --
  // only the grid's own idea of where they are.
  const [layoutGeneration, setLayoutGeneration] = useState(0);

  useEffect(() => {
    location.setSearch({ edit: editingLayout ? true : null }, true);
  }, [editingLayout]);

  const updateDashboardLayout = useCallback(
    (positions) => {
      pendingPositions.current = positions;
      const changed = !isEmpty(getChangedPositions(widgets, positions));
      setHasUnsavedChanges(changed);
      setDashboardStatus((status) => {
        // A failed save keeps saying so until another one is tried, rather
        // than being talked over by the next drag.
        if (status === DashboardStatusEnum.SAVING_FAILED) {
          return status;
        }
        return changed ? DashboardStatusEnum.UNSAVED : DashboardStatusEnum.SAVED;
      });
    },
    [widgets]
  );

  /** Resolves true when there is nothing left unsaved. */
  const saveDashboardLayout = useCallback(() => {
    if (!canEditDashboard) {
      setDashboardStatus(DashboardStatusEnum.SAVED);
      return Promise.resolve(true);
    }

    const changedPositions = getChangedPositions(widgets, pendingPositions.current);
    if (isEmpty(changedPositions)) {
      setDashboardStatus(DashboardStatusEnum.SAVED);
      setHasUnsavedChanges(false);
      return Promise.resolve(true);
    }

    setDashboardStatus(DashboardStatusEnum.SAVING);
    return Promise.all(
      map(changedPositions, (position, id) => {
        const widget = find(widgets, { id: Number(id) });
        return widget ? widget.save("options", { position }) : Promise.resolve();
      })
    )
      .then(() => {
        setDashboardStatus(DashboardStatusEnum.SAVED);
        setHasUnsavedChanges(false);
        return true;
      })
      .catch(() => {
        // Left in edit mode on purpose: the arrangement is still only here,
        // and leaving now would lose it.
        setDashboardStatus(DashboardStatusEnum.SAVING_FAILED);
        notification.error("Error saving changes.");
        return false;
      });
  }, [canEditDashboard, widgets]);

  const discardDashboardLayout = useCallback(() => {
    pendingPositions.current = {};
    setHasUnsavedChanges(false);
    setDashboardStatus(DashboardStatusEnum.SAVED);
    setLayoutGeneration((generation) => generation + 1);
  }, []);

  const setEditing = useCallback(
    (editing) => {
      setEditingLayout(canEditDashboard && editing);
    },
    [canEditDashboard]
  );

  return {
    editingLayout: canEditDashboard && editingLayout,
    setEditingLayout: setEditing,
    updateDashboardLayout,
    saveDashboardLayout,
    discardDashboardLayout,
    hasUnsavedChanges,
    layoutGeneration,
    dashboardStatus,
  };
}
