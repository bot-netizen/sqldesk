import React, { useCallback } from "react";
import PropTypes from "prop-types";
import { filter, isFunction } from "lodash";
import Dropdown from "antd/lib/dropdown";
import Menu from "antd/lib/menu";
import Modal from "antd/lib/modal";
import MoreOutlinedIcon from "@ant-design/icons/MoreOutlined";
import Link from "@/components/Link";
import PlainButton from "@/components/PlainButton";
import PermissionsEditorDialog from "@/components/PermissionsEditorDialog";
import notification from "@/services/notification";
import { currentUser } from "@/services/auth";

import "./ListItemActions.less";

/*
  Row actions for the list pages.

  Permissions are admin-only HERE, which is a narrower rule than the API
  enforces: POST/DELETE on an object's ACL calls require_admin_or_owner, so
  an owner can still change sharing through the object's own page or the
  API directly. Hiding the entry is presentation, not enforcement — if
  admin-only is meant to be a real restriction, tealdash/handlers/permissions.py
  has to change too.
*/
export function canManagePermissions() {
  return !!currentUser.isAdmin;
}

function confirmDestructive({ title, content, okText }) {
  return new Promise((resolve) => {
    Modal.confirm({
      title,
      content,
      okText,
      okType: "danger",
      maskClosable: true,
      autoFocusButton: null,
      onOk: () => resolve(true),
      onCancel: () => resolve(false),
    });
  });
}

export default function ListItemActions({ item, editUrl, aclUrl, aclContext, onDelete, deleteLabel, deleteConfirm }) {
  const showPermissions = useCallback(() => {
    PermissionsEditorDialog.showModal({ aclUrl, context: aclContext, author: item.user });
  }, [aclUrl, aclContext, item.user]);

  const remove = useCallback(async () => {
    const confirmed = await confirmDestructive(deleteConfirm);
    if (!confirmed) {
      return;
    }
    try {
      await onDelete(item);
      notification.success(`${deleteLabel}d "${item.name}".`);
    } catch (error) {
      // The API is the authority on whether this was allowed; surface its
      // refusal rather than assuming the click implied permission.
      notification.error(`${deleteLabel} failed.`, error && error.message);
    }
  }, [onDelete, item, deleteLabel, deleteConfirm]);

  const entries = filter([
    editUrl && (
      <Menu.Item key="edit">
        <Link href={editUrl} data-test="ListItemEdit">
          Edit
        </Link>
      </Menu.Item>
    ),
    aclUrl && canManagePermissions() && (
      <Menu.Item key="permissions">
        <PlainButton onClick={showPermissions} data-test="ListItemPermissions">
          Manage permissions
        </PlainButton>
      </Menu.Item>
    ),
    isFunction(onDelete) && <Menu.Divider key="divider" />,
    isFunction(onDelete) && (
      <Menu.Item key="delete" danger>
        <PlainButton onClick={remove} data-test="ListItemDelete">
          {deleteLabel}
        </PlainButton>
      </Menu.Item>
    ),
  ]);

  if (entries.length === 0) {
    return null;
  }

  return (
    <Dropdown
      overlay={<Menu className="list-item-actions-menu">{entries}</Menu>}
      trigger={["click"]}
      placement="bottomRight"
    >
      <PlainButton
        className="list-item-actions-trigger"
        data-test="ListItemActions"
        aria-label={`Actions for ${item.name}`}
        // The row is a link; keep the menu click from following it.
        onClick={(event) => event.stopPropagation()}
      >
        <MoreOutlinedIcon aria-hidden="true" />
      </PlainButton>
    </Dropdown>
  );
}

ListItemActions.propTypes = {
  // eslint-disable-next-line react/forbid-prop-types
  item: PropTypes.object.isRequired,
  editUrl: PropTypes.string,
  aclUrl: PropTypes.string,
  aclContext: PropTypes.oneOf(["query", "dashboard"]),
  onDelete: PropTypes.func,
  deleteLabel: PropTypes.string,
  deleteConfirm: PropTypes.shape({
    title: PropTypes.string,
    content: PropTypes.node,
    okText: PropTypes.string,
  }),
};

ListItemActions.defaultProps = {
  editUrl: null,
  aclUrl: null,
  aclContext: "query",
  onDelete: null,
  deleteLabel: "Archive",
  deleteConfirm: { title: "Archive", content: "Are you sure?", okText: "Archive" },
};
