import React, { useState } from "react";
import cx from "classnames";
import PropTypes from "prop-types";
import { map, includes } from "lodash";
import Button from "antd/lib/button";
import Checkbox from "antd/lib/checkbox";
import Dropdown from "antd/lib/dropdown";
import Menu from "antd/lib/menu";
import EllipsisOutlinedIcon from "@ant-design/icons/EllipsisOutlined";
import PauseCircleOutlinedIcon from "@ant-design/icons/PauseCircleOutlined";
import PlayCircleOutlinedIcon from "@ant-design/icons/PlayCircleOutlined";
import Modal from "antd/lib/modal";
import Tooltip from "@/components/Tooltip";
import FavoritesControl from "@/components/FavoritesControl";
import EditInPlace from "@/components/EditInPlace";
import ShareDashboardButton from "./ShareDashboardButton";
import DashboardFilters from "./DashboardFilters";
import LiveBadge, { LIVE_INTERVAL_LABELS } from "./LiveBadge";
import PlainButton from "@/components/PlainButton";
import { DashboardTagsControl } from "@/components/tags-control/TagsControl";
import getTags from "@/services/getTags";
import { clientConfig } from "@/services/auth";
import { policy } from "@/services/policy";
import recordEvent from "@/services/recordEvent";
import { durationHumanize } from "@/lib/utils";
import { DashboardStatusEnum } from "../hooks/useDashboard";

import "./DashboardHeader.less";

function getDashboardTags() {
  return getTags("api/dashboards/tags").then((tags) => map(tags, (t) => t.name));
}

function buttonType(value) {
  return value ? "primary" : "default";
}

function DashboardPageTitle({ dashboardConfiguration }) {
  const { dashboard, canEditDashboard, updateDashboard, editingLayout } = dashboardConfiguration;
  return (
    <div className="title-with-tags">
      <div className="page-title">
        <FavoritesControl item={dashboard} />
        <h3>
          <EditInPlace
            isEditable={editingLayout}
            onDone={(name) => updateDashboard({ name })}
            value={dashboard.name}
            ignoreBlanks
          />
        </h3>
        <Tooltip title={dashboard.user.name} placement="bottom">
          <img src={dashboard.user.profile_image_url} className="profile-image" alt={dashboard.user.name} />
        </Tooltip>
      </div>
      <DashboardTagsControl
        tags={dashboard.tags}
        isDraft={dashboard.is_draft}
        isArchived={dashboard.is_archived}
        canEdit={canEditDashboard}
        getAvailableTags={getDashboardTags}
        onEdit={(tags) => updateDashboard({ tags })}
      />
    </div>
  );
}

DashboardPageTitle.propTypes = {
  dashboardConfiguration: PropTypes.object.isRequired, // eslint-disable-line react/forbid-prop-types
};

function RefreshButton({ dashboardConfiguration }) {
  const { refreshRate, setRefreshRate, disableRefreshRate, refreshing, refreshDashboard } = dashboardConfiguration;
  const allowedIntervals = policy.getDashboardRefreshIntervals();
  const refreshRateOptions = clientConfig.dashboardRefreshIntervals;
  const onRefreshRateSelected = ({ key }) => {
    const parsedRefreshRate = parseFloat(key);
    if (parsedRefreshRate) {
      setRefreshRate(parsedRefreshRate);
      refreshDashboard();
    } else {
      disableRefreshRate();
    }
  };
  return (
    <Button.Group>
      <Tooltip title={refreshRate ? `Auto Refreshing every ${durationHumanize(refreshRate)}` : null}>
        <Button type={buttonType(refreshRate)} onClick={() => refreshDashboard()}>
          <i className={cx("zmdi zmdi-refresh m-r-5", { "zmdi-hc-spin": refreshing })} aria-hidden="true" />
          {refreshRate ? durationHumanize(refreshRate) : "Refresh"}
        </Button>
      </Tooltip>
      <Dropdown
        trigger={["click"]}
        placement="bottomRight"
        overlay={
          <Menu onClick={onRefreshRateSelected} selectedKeys={[`${refreshRate}`]} data-test="DashboardRefreshRateMenu">
            {refreshRateOptions.map((option) => (
              <Menu.Item key={`${option}`} disabled={!includes(allowedIntervals, option)}>
                {durationHumanize(option)}
              </Menu.Item>
            ))}
            {refreshRate && <Menu.Item key={null}>Disable auto refresh</Menu.Item>}
          </Menu>
        }
      >
        <Button className="icon-button hidden-xs" type={buttonType(refreshRate)} data-test="DashboardRefreshRateButton">
          <i className="fa fa-angle-down" aria-hidden="true" />
          <span className="sr-only">Split button!</span>
        </Button>
      </Dropdown>
    </Button.Group>
  );
}

RefreshButton.propTypes = {
  dashboardConfiguration: PropTypes.object.isRequired, // eslint-disable-line react/forbid-prop-types
};

function LiveControl({ dashboardConfiguration }) {
  const { live, canManageLive, changeLive } = dashboardConfiguration;
  return (
    <span className="live-control">
      <LiveBadge live={live} />
      {canManageLive && (
        <Button className="m-l-5" onClick={() => changeLive({ paused: !live.paused })} data-test="LivePauseButton">
          {live.paused ? (
            <React.Fragment>
              <PlayCircleOutlinedIcon aria-hidden="true" /> Resume
            </React.Fragment>
          ) : (
            <React.Fragment>
              <PauseCircleOutlinedIcon aria-hidden="true" /> Pause
            </React.Fragment>
          )}
        </Button>
      )}
    </span>
  );
}

LiveControl.propTypes = {
  dashboardConfiguration: PropTypes.object.isRequired, // eslint-disable-line react/forbid-prop-types
};

function DashboardMoreOptionsButton({ dashboardConfiguration }) {
  const {
    dashboard,
    setEditingLayout,
    togglePublished,
    archiveDashboard,
    managePermissions,
    gridDisabled,
    isDashboardOwnerOrAdmin,
    isDuplicating,
    duplicateDashboard,
    live,
    canManageLive,
    changeLive,
  } = dashboardConfiguration;

  const archive = () => {
    Modal.confirm({
      title: "Archive Dashboard",
      content: `Are you sure you want to archive the "${dashboard.name}" dashboard?`,
      okText: "Archive",
      okType: "danger",
      onOk: archiveDashboard,
      maskClosable: true,
      autoFocusButton: null,
    });
  };

  return (
    <Dropdown
      trigger={["click"]}
      placement="bottomRight"
      overlay={
        // Submenus open on click: a hover target that moves is hard to hit on
        // a touch screen, and harder still for a test to drive.
        <Menu data-test="DashboardMoreButtonMenu" triggerSubMenuAction="click">
          <Menu.Item className={cx({ hidden: gridDisabled })}>
            <PlainButton onClick={() => setEditingLayout(true)}>Edit</PlainButton>
          </Menu.Item>
          {!isDuplicating && dashboard.canEdit() && (
            <Menu.Item>
              <PlainButton onClick={duplicateDashboard}>
                Fork <i className="fa fa-external-link m-l-5" aria-hidden="true" />
                <span className="sr-only">(opens in a new tab)</span>
              </PlainButton>
            </Menu.Item>
          )}
          {clientConfig.showPermissionsControl && isDashboardOwnerOrAdmin && (
            <Menu.Item>
              <PlainButton onClick={managePermissions}>Manage Permissions</PlainButton>
            </Menu.Item>
          )}
          {canManageLive && (
            <Menu.SubMenu key="live" title={<span data-test="LiveMenu">{live ? "Live" : "Make live"}</span>}>
              {Object.keys(LIVE_INTERVAL_LABELS).map((interval) => (
                <Menu.Item key={`live-${interval}`}>
                  <PlainButton
                    onClick={() => changeLive({ interval: Number(interval) })}
                    data-test={`LiveInterval.${interval}`}
                  >
                    {live && live.interval === Number(interval) && (
                      <i className="fa fa-check m-r-5" aria-hidden="true" />
                    )}
                    Refresh {LIVE_INTERVAL_LABELS[interval]}
                  </PlainButton>
                </Menu.Item>
              ))}
              {live && <Menu.Divider />}
              {live && (
                <Menu.Item key="live-off">
                  <PlainButton onClick={() => changeLive({ interval: null })} data-test="LiveOff">
                    Turn off live
                  </PlainButton>
                </Menu.Item>
              )}
            </Menu.SubMenu>
          )}
          {!clientConfig.disablePublish && !dashboard.is_draft && (
            <Menu.Item>
              <PlainButton onClick={togglePublished}>Unpublish</PlainButton>
            </Menu.Item>
          )}
          <Menu.Item>
            <PlainButton onClick={archive}>Archive</PlainButton>
          </Menu.Item>
        </Menu>
      }
    >
      <Button className="icon-button m-l-5" data-test="DashboardMoreButton" aria-label="More actions">
        <EllipsisOutlinedIcon rotate={90} aria-hidden="true" />
      </Button>
    </Dropdown>
  );
}

DashboardMoreOptionsButton.propTypes = {
  dashboardConfiguration: PropTypes.object.isRequired, // eslint-disable-line react/forbid-prop-types
};

function DashboardControl({ dashboardConfiguration, headerExtra, onParametersEdit }) {
  const {
    dashboard,
    togglePublished,
    canEditDashboard,
    fullscreen,
    toggleFullscreen,
    showShareDashboardDialog,
    updateDashboard,
    live,
    editingLayout,
  } = dashboardConfiguration;
  const showPublishButton = dashboard.is_draft;
  // A live dashboard is refreshed by the server; its header says so instead.
  const showRefreshButton = !live;
  const showFullscreenButton = !dashboard.is_draft;
  const canShareDashboard = canEditDashboard && !dashboard.is_draft;
  const showShareButton = !clientConfig.disablePublicUrls && (dashboard.publicAccessEnabled || canShareDashboard);
  const showMoreOptionsButton = canEditDashboard;

  const unarchiveDashboard = () => {
    recordEvent("unarchive", "dashboard", dashboard.id);
    updateDashboard({ is_archived: false }, false);
  };
  return (
    <div className="dashboard-control">
      {dashboard.can_edit && dashboard.is_archived && <Button onClick={unarchiveDashboard}>Unarchive</Button>}
      {!dashboard.is_archived && (
        <span className="hidden-print">
          {showPublishButton && (
            <Button className="m-r-5 hidden-xs" onClick={togglePublished}>
              <span className="fa fa-paper-plane m-r-5" /> Publish
            </Button>
          )}
          {/* Beside Refresh rather than in a band of its own above the grid. */}
          {!editingLayout && (
            <DashboardFilters dashboardConfiguration={dashboardConfiguration} onParametersEdit={onParametersEdit} />
          )}
          {showRefreshButton && <RefreshButton dashboardConfiguration={dashboardConfiguration} />}
          {live && <LiveControl dashboardConfiguration={dashboardConfiguration} />}
          <ShareDashboardButton
            dashboard={dashboard}
            // The grid, not the page: a shared snapshot should not carry the
            // app's navigation or this header.
            getExportTarget={() => document.getElementById("dashboard-container")}
            onShowPublicLink={showShareButton ? showShareDashboardDialog : null}
          />
          {showFullscreenButton && (
            <Tooltip className="hidden-xs" title="Enable/Disable Fullscreen display">
              <Button
                type={buttonType(fullscreen)}
                className="icon-button m-l-5"
                onClick={toggleFullscreen}
                aria-label="Toggle fullscreen display"
              >
                <i className="zmdi zmdi-fullscreen" aria-hidden="true" />
              </Button>
            </Tooltip>
          )}
          {headerExtra}
          {showMoreOptionsButton && <DashboardMoreOptionsButton dashboardConfiguration={dashboardConfiguration} />}
        </span>
      )}
    </div>
  );
}

DashboardControl.propTypes = {
  dashboardConfiguration: PropTypes.object.isRequired, // eslint-disable-line react/forbid-prop-types
  headerExtra: PropTypes.node,
  onParametersEdit: PropTypes.func,
};

export function DashboardEditControl({ dashboardConfiguration, headerExtra }) {
  const {
    dashboard,
    updateDashboard,
    setEditingLayout,
    dashboardStatus,
    hasUnsavedChanges,
    saveDashboardLayout,
    discardDashboardLayout,
    saveDashboardParameters,
  } = dashboardConfiguration;
  const [saving, setSaving] = useState(false);

  const handleDoneEditing = () => {
    setSaving(true);
    saveDashboardParameters()
      .then(() => saveDashboardLayout())
      // Only leaves edit mode once the layout is actually stored: the
      // arrangement exists nowhere else, so leaving on a failed save would
      // throw it away.
      .then((saved) => {
        if (saved) {
          setEditingLayout(false);
        }
      })
      .finally(() => setSaving(false));
  };

  const handleDiscard = () => {
    if (!hasUnsavedChanges) {
      setEditingLayout(false);
      return;
    }
    Modal.confirm({
      title: "Discard changes?",
      content: "The widgets you moved or resized will go back where they were.",
      okText: "Discard",
      okType: "danger",
      cancelText: "Keep editing",
      onOk: () => {
        discardDashboardLayout();
        setEditingLayout(false);
      },
    });
  };

  let status;
  if (dashboardStatus === DashboardStatusEnum.SAVING) {
    status = (
      <span className="save-status" data-saving>
        Saving
      </span>
    );
  } else if (dashboardStatus === DashboardStatusEnum.SAVING_FAILED) {
    status = (
      <span className="save-status" data-error>
        Saving Failed
      </span>
    );
  } else if (dashboardStatus === DashboardStatusEnum.UNSAVED) {
    // Said plainly, because it is now true: moving a widget changes nothing
    // until this is pressed.
    status = (
      <span className="save-status" data-unsaved>
        Unsaved changes
      </span>
    );
  } else {
    status = <span className="save-status">No changes</span>;
  }
  return (
    <div className="dashboard-control">
      {/*
        Beside Done Editing rather than in a band of its own across the top
        of the dashboard: it is one checkbox, and that band cost a widget's
        worth of height for it.
      */}
      <Checkbox
        className="dashboard-filters-toggle"
        checked={!!dashboard.dashboard_filters_enabled}
        onChange={({ target }) => updateDashboard({ dashboard_filters_enabled: target.checked })}
        data-test="DashboardFiltersCheckbox"
      >
        Dashboard level filters
      </Checkbox>
      {status}
      <Button className="m-r-5" onClick={handleDiscard} data-test="DashboardDiscardButton">
        Discard
      </Button>
      <Button loading={saving} type="primary" onClick={handleDoneEditing} data-test="DashboardDoneEditingButton">
        {!saving && <i className="fa fa-check m-r-5" aria-hidden="true" />}
        {dashboardStatus === DashboardStatusEnum.SAVING_FAILED ? "Retry" : "Done Editing"}
      </Button>
      {headerExtra}
    </div>
  );
}

DashboardEditControl.propTypes = {
  dashboardConfiguration: PropTypes.object.isRequired, // eslint-disable-line react/forbid-prop-types
  headerExtra: PropTypes.node,
};

export default function DashboardHeader({ dashboardConfiguration, headerExtra, onParametersEdit }) {
  const { editingLayout } = dashboardConfiguration;
  const DashboardControlComponent = editingLayout ? DashboardEditControl : DashboardControl;

  return (
    <div className="dashboard-header">
      <DashboardPageTitle dashboardConfiguration={dashboardConfiguration} />
      <DashboardControlComponent
        dashboardConfiguration={dashboardConfiguration}
        headerExtra={headerExtra}
        onParametersEdit={onParametersEdit}
      />
    </div>
  );
}

DashboardHeader.propTypes = {
  dashboardConfiguration: PropTypes.object.isRequired, // eslint-disable-line react/forbid-prop-types
  headerExtra: PropTypes.node,
  onParametersEdit: PropTypes.func,
};
