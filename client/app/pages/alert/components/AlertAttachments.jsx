import React from "react";
import PropTypes from "prop-types";
import { filter, map, toLower, includes } from "lodash";

import Button from "antd/lib/button";
import CloseOutlinedIcon from "@ant-design/icons/CloseOutlined";
import PlusOutlinedIcon from "@ant-design/icons/PlusOutlined";

import SelectItemsDialog from "@/components/SelectItemsDialog";
import ListItemAddon from "@/components/groups/ListItemAddon";
import PlainButton from "@/components/PlainButton";
import Tooltip from "@/components/Tooltip";
import { Dashboard } from "@/services/dashboard";
import { Query } from "@/services/query";

import "./AlertAttachments.less";

/*
  Pictures to send with an alert.

  A picker rather than a box to paste links into: the ids are then real, the
  permissions are checked as you choose, and a mistyped URL cannot become an
  attachment that silently never arrives.

  Capped, and the cap is the point -- an alert carrying twenty dashboards
  takes minutes to send and arrives as something nobody opens.
*/

export const MAX_ATTACHMENTS = 5;

const DASHBOARD = "dashboard";
const QUERY = "query";

function label(attachment) {
  return attachment.name || `${attachment.type} ${attachment.id}`;
}

function searchBoth(term) {
  const text = toLower(term || "");
  return Promise.all([
    Dashboard.query({ q: text, page_size: 10 }).catch(() => ({ results: [] })),
    Query.query({ q: text, page_size: 10 }).catch(() => ({ results: [] })),
  ]).then(([dashboards, queries]) => [
    ...map(dashboards.results, (d) => ({
      type: DASHBOARD,
      id: d.id,
      name: d.name,
      // A dashboard can only be drawn if it has a shareable link; nothing
      // here creates one, because making a dashboard public is the owner's
      // decision and not a side effect of attaching it to an alert.
      shared: !!d.public_url,
    })),
    ...map(queries.results, (q) => ({ type: QUERY, id: q.id, name: q.name, shared: true })),
  ]);
}

export default function AlertAttachments({ value, onChange, editMode }) {
  const attachments = value || [];

  const remove = (attachment) =>
    onChange(filter(attachments, (a) => !(a.type === attachment.type && a.id === attachment.id)));

  const add = () => {
    SelectItemsDialog.showModal({
      width: 570,
      showCount: true,
      dialogTitle: "Attach a dashboard or query",
      inputPlaceholder: "Search dashboards and queries…",
      searchItems: searchBoth,
      renderItem: (item, { isSelected }) => {
        const alreadyAttached = !!filter(attachments, (a) => a.type === item.type && a.id === item.id).length;
        return {
          content: (
            <div className="alert-attachment-option">
              <span className="alert-attachment-kind">{item.type}</span>
              <span className="flex-fill">{item.name}</span>
              {!item.shared && (
                <Tooltip title="This dashboard has no shareable link, so there is nothing to draw. Share it first.">
                  <span className="alert-attachment-warning">not shared</span>
                </Tooltip>
              )}
              <ListItemAddon isSelected={isSelected} alreadyInGroup={alreadyAttached} deselectedIcon="fa-plus" />
            </div>
          ),
          isDisabled: alreadyAttached,
          className: isSelected || alreadyAttached ? "selected" : "",
        };
      },
    }).onClose((items) => {
      const chosen = filter(
        items,
        (item) =>
          !includes(
            map(attachments, (a) => `${a.type}:${a.id}`),
            `${item.type}:${item.id}`
          )
      );
      onChange([...attachments, ...chosen].slice(0, MAX_ATTACHMENTS));
      return Promise.resolve();
    });
  };

  if (!editMode) {
    if (!attachments.length) {
      return <span className="text-muted">No attachments</span>;
    }
    return (
      <ul className="alert-attachments">
        {attachments.map((attachment) => (
          <li key={`${attachment.type}:${attachment.id}`}>
            <span className="alert-attachment-kind">{attachment.type}</span>
            <span className="flex-fill">{label(attachment)}</span>
          </li>
        ))}
      </ul>
    );
  }

  return (
    <div className="alert-attachments-editor" data-test="AlertAttachments">
      <ul className="alert-attachments">
        {attachments.map((attachment) => (
          <li key={`${attachment.type}:${attachment.id}`}>
            <span className="alert-attachment-kind">{attachment.type}</span>
            <span className="flex-fill">{label(attachment)}</span>
            <Tooltip title="Remove" mouseEnterDelay={0.5}>
              <PlainButton
                className="alert-attachment-remove"
                onClick={() => remove(attachment)}
                aria-label={`Remove ${label(attachment)}`}
              >
                <CloseOutlinedIcon />
              </PlainButton>
            </Tooltip>
          </li>
        ))}
      </ul>
      <Button
        type="dashed"
        onClick={add}
        disabled={attachments.length >= MAX_ATTACHMENTS}
        data-test="AddAlertAttachment"
      >
        <PlusOutlinedIcon aria-hidden="true" /> Add
      </Button>
      <div className="alert-attachments-note">
        {attachments.length >= MAX_ATTACHMENTS
          ? `That is the most an alert can carry (${MAX_ATTACHMENTS}).`
          : "Sent as images in the alert email."}
      </div>
    </div>
  );
}

AlertAttachments.propTypes = {
  value: PropTypes.arrayOf(PropTypes.object), // eslint-disable-line react/forbid-prop-types
  onChange: PropTypes.func.isRequired,
  editMode: PropTypes.bool,
};

AlertAttachments.defaultProps = { value: [], editMode: false };
