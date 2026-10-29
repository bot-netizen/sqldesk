import { filter, includes, map, without } from "lodash";
import React, { useState, useEffect, useCallback } from "react";
import PropTypes from "prop-types";
import Modal from "antd/lib/modal";
import Checkbox from "antd/lib/checkbox";
import { wrap as wrapDialog, DialogPropType } from "@/components/DialogWrapper";
import { Query } from "@/services/query";
import Spinner from "@/components/Spinner";
import notification from "@/services/notification";

/**
 * Choose which of a query's visualizations this widget offers as tabs.
 *
 * Only this query's. Every tab draws the result the widget has already
 * fetched, which is what makes a tab free -- three widgets on one query
 * fetch and parse it three times, one widget with three tabs fetches it
 * once. The server enforces the same rule, so a tab from elsewhere could
 * not be saved even if this dialog offered it.
 *
 * The widget's own visualization is always the first tab and is not listed:
 * it cannot be removed without removing the widget.
 */
function ChooseWidgetTabsDialog({ dialog, widget }) {
  const [available, setAvailable] = useState(null);
  const [selected, setSelected] = useState(() =>
    map(
      filter(widget.getTabs(), (one) => one.id !== widget.visualization.id),
      "id"
    )
  );
  const [saving, setSaving] = useState(false);

  const queryId = widget.visualization.query.id;

  useEffect(() => {
    let cancelled = false;
    // The dashboard payload does not carry a query's other visualizations --
    // a dashboard is the heaviest thing the application sends and that list
    // is only wanted here, once, by somebody editing.
    Query.get({ id: queryId })
      .then((query) => {
        if (!cancelled) {
          // Charts only, the same rule the server stores by. Offering a
          // counter here would write a tab the server then drops, which
          // reads as the dialog having silently failed.
          setAvailable(
            filter(query.visualizations, (one) => one.id !== widget.visualization.id && one.type === "CHART")
          );
        }
      })
      .catch(() => {
        if (!cancelled) {
          setAvailable([]);
          notification.error("Could not load this query's other visualizations.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [queryId, widget.visualization.id]);

  const toggle = useCallback((id, on) => {
    // Order is the tab order, so a newly ticked one goes on the end rather
    // than wherever it happens to sit in the query's own list.
    setSelected((current) => (on ? [...current, id] : without(current, id)));
  }, []);

  const save = useCallback(() => {
    setSaving(true);
    // Assigned, not merged: `save(key, value)` deep-merges, and a deep merge
    // of arrays joins them by index -- replacing [7, 9] with [5] would leave
    // [5, 9]. The whole options blob goes as it stands instead.
    if (selected.length) {
      widget.options.tabs = selected;
    } else {
      delete widget.options.tabs;
    }
    widget
      .save()
      .then(() => dialog.close(widget))
      .catch(() => {
        setSaving(false);
        notification.error("Could not save the tabs.");
      });
  }, [dialog, selected, widget]);

  return (
    <Modal
      {...dialog.props}
      title="Choose tabs"
      okText="Save"
      okButtonProps={{ loading: saving, "data-test": "SaveWidgetTabs" }}
      onOk={save}
    >
      <p className="m-b-15">
        Show more than one of this query's visualizations in this widget, chosen from a strip at the top. They all draw
        the same result, so the query is still run once.
      </p>
      {available === null && <Spinner />}
      {available !== null && available.length === 0 && (
        <p className="text-muted" data-test="NoOtherVisualizations">
          This query has no other charts. Add one on the query page and it will appear here — tabs are for charts,
          because a counter is one number and a table is already a grid of them.
        </p>
      )}
      {map(available || [], (one) => (
        <div key={one.id} className="m-b-5">
          <Checkbox
            data-test={`WidgetTabOption${one.id}`}
            checked={includes(selected, one.id)}
            onChange={(event) => toggle(one.id, event.target.checked)}
          >
            {one.name}
          </Checkbox>
        </div>
      ))}
    </Modal>
  );
}

ChooseWidgetTabsDialog.propTypes = {
  dialog: DialogPropType.isRequired,
  widget: PropTypes.object.isRequired,
};

export default wrapDialog(ChooseWidgetTabsDialog);
