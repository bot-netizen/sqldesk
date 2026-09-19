import React, { useState, useEffect } from "react";
import PropTypes from "prop-types";
import Button from "antd/lib/button";
import Divider from "antd/lib/divider";
import Checkbox from "antd/lib/checkbox";

import * as Sidebar from "@/components/items-list/components/Sidebar";
import { ControllerType } from "@/components/items-list/ItemsList";
import DeleteGroupButton from "./DeleteGroupButton";

import { currentUser } from "@/services/auth";
import Group from "@/services/group";
import notification from "@/services/notification";

const MANAGE_LIVE_PERMISSION = "manage_live_dashboards";

/*
  Whether this group's members may turn dashboards live. Admins can always;
  this lets them hand it to anyone else, including everybody through the
  default group.
*/
function LivePermissionToggle({ group }) {
  const [granted, setGranted] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setGranted((group.permissions || []).includes(MANAGE_LIVE_PERMISSION));
  }, [group]);

  const toggle = (event) => {
    const next = event.target.checked;
    setSaving(true);
    Group.setPermissions(group, { [MANAGE_LIVE_PERMISSION]: next })
      .then((updated) => {
        setGranted((updated.permissions || []).includes(MANAGE_LIVE_PERMISSION));
        notification.success(
          next ? "Members can now make dashboards live." : "Members can no longer make dashboards live."
        );
      })
      .catch(() => notification.error("Could not change the permission."))
      .finally(() => setSaving(false));
  };

  return (
    <Checkbox checked={granted} disabled={saving} onChange={toggle} data-test="GroupLivePermission">
      Members can make dashboards live
    </Checkbox>
  );
}

LivePermissionToggle.propTypes = {
  group: PropTypes.object.isRequired, // eslint-disable-line react/forbid-prop-types
};

export default function DetailsPageSidebar({
  controller,
  group,
  items,
  canAddMembers,
  onAddMembersClick,
  canAddDataSources,
  onAddDataSourcesClick,
  onGroupDeleted,
}) {
  const canRemove = group && currentUser.isAdmin && group.type !== "builtin";
  // The admin group has every permission already.
  const canGrantLive = group && currentUser.isAdmin && !(group.permissions || []).includes("admin");

  return (
    <React.Fragment>
      <Sidebar.Menu items={items} selected={controller.params.currentPage} />
      {canAddMembers && (
        <Button className="w-100 m-t-5" type="primary" onClick={onAddMembersClick}>
          <i className="fa fa-plus m-r-5" aria-hidden="true" />
          Add Members
        </Button>
      )}
      {canAddDataSources && (
        <Button className="w-100 m-t-5" type="primary" onClick={onAddDataSourcesClick}>
          <i className="fa fa-plus m-r-5" aria-hidden="true" />
          Add Data Sources
        </Button>
      )}
      {canGrantLive && (
        <React.Fragment>
          <Divider dashed className="m-t-10 m-b-10" />
          <LivePermissionToggle group={group} />
        </React.Fragment>
      )}
      {canRemove && (
        <React.Fragment>
          <Divider dashed className="m-t-10 m-b-10" />
          <DeleteGroupButton className="w-100" group={group} onClick={onGroupDeleted}>
            Delete Group
          </DeleteGroupButton>
        </React.Fragment>
      )}
    </React.Fragment>
  );
}

DetailsPageSidebar.propTypes = {
  controller: ControllerType.isRequired,
  group: PropTypes.object, // eslint-disable-line react/forbid-prop-types
  items: PropTypes.array.isRequired, // eslint-disable-line react/forbid-prop-types

  canAddMembers: PropTypes.bool,
  onAddMembersClick: PropTypes.func,

  canAddDataSources: PropTypes.bool,
  onAddDataSourcesClick: PropTypes.func,

  onGroupDeleted: PropTypes.func,
};

DetailsPageSidebar.defaultProps = {
  group: null,

  canAddMembers: false,
  onAddMembersClick: null,

  canAddDataSources: false,
  onAddDataSourcesClick: null,

  onGroupDeleted: null,
};
