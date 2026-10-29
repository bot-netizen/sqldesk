import React, { useEffect, useState } from "react";
import cx from "classnames";
import PropTypes from "prop-types";
import { map, includes } from "lodash";
import Button from "antd/lib/button";
import Checkbox from "antd/lib/checkbox";
import Dropdown from "antd/lib/dropdown";
import Menu from "antd/lib/menu";
import { axios } from "@/services/axios";
import UserAvatar from "@/components/UserAvatar";
import EllipsisOutlinedIcon from "@ant-design/icons/EllipsisOutlined";
import PauseCircleOutlinedIcon from "@ant-design/icons/PauseCircleOutlined";
import PlayCircleOutlinedIcon from "@ant-design/icons/PlayCircleOutlined";
import Modal from "antd/lib/modal";
import Popover from "antd/lib/popover";
import Tooltip from "@/components/Tooltip";
import TimeAgo from "@/components/TimeAgo";
import FavoritesControl from "@/components/FavoritesControl";
import EditInPlace from "@/components/EditInPlace";
import ShareDashboardButton from "./ShareDashboardButton";
import DashboardFilters from "./DashboardFilters";
import LiveBadge, { LIVE_INTERVAL_LABELS, intervalsFor } from "./LiveBadge";
import VerifyDashboardDialog from "./VerifyDashboardDialog";
import PlainButton from "@/components/PlainButton";
import { DashboardTagsControl } from "@/components/tags-control/TagsControl";
import getTags from "@/services/getTags";
import { clientConfig, currentUser } from "@/services/auth";
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

// Exported for its own test: what a dashboard says it is, beside its name.
/*
  Who checked this dashboard, and what they checked.

  A popover on click rather than a tooltip on hover, because the note is the
  point and has to be readable on a phone. When the charts or their queries
  have changed since, the badge says so instead of vouching for something it
  never saw.
*/
export function VerifiedBadge({ verification }) {
  if (!verification) {
    return null;
  }
  const changed = !!verification.changed_since;
  const content = (
    <div className="dashboard-verified-note" data-test="VerificationNote">
      <div>
        <strong>{verification.by || "Somebody"}</strong> verified this <TimeAgo date={verification.at} />.
      </div>
      <p className="m-t-5 m-b-0">{verification.note}</p>
      {changed && (
        <p className="m-t-5 m-b-0 text-warning" data-test="VerificationChanged">
          The dashboard has changed since: a chart or the query behind one is not what was checked.
        </p>
      )}
    </div>
  );
  return (
    <Popover content={content} trigger="click" placement="bottom">
      <button
        type="button"
        className={cx("dashboard-verified-chip", { "dashboard-verified-chip--changed": changed })}
        data-test="VerifiedBadge"
      >
        <i className={cx("fa", changed ? "fa-exclamation-circle" : "fa-check-circle")} aria-hidden="true" />{" "}
        {changed ? "verified, then changed" : "verified"}
      </button>
    </Popover>
  );
}

VerifiedBadge.propTypes = {
  verification: PropTypes.shape({
    by: PropTypes.string,
    at: PropTypes.string,
    note: PropTypes.string,
    changed_since: PropTypes.bool,
  }),
};

VerifiedBadge.defaultProps = {
  verification: null,
};

export function DashboardPageTitle({ dashboardConfiguration }) {
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
        {/*
          What this dashboard is, beside its name. The badge to the right says
          what it is *doing* -- live, or paused -- and the two are different
          questions: an ordinary dashboard can be live too, so "live" has never
          meant "fed by a stream". A chart standing still is read very
          differently depending on which of them you are looking at.
        */}
        {dashboard.is_streaming && (
          <Tooltip
            title="Fed by streaming queries. It refreshes in seconds while somebody is watching, and pauses when nobody is."
            placement="bottom"
          >
            <span className="dashboard-streaming-chip" data-test="StreamingChip">
              streaming
            </span>
          </Tooltip>
        )}
        <VerifiedBadge verification={dashboard.verification} />
        <Tooltip title={dashboard.user.name} placement="bottom">
          <UserAvatar user={dashboard.user} size={24} className="profile-image" />
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

/**
 * Whether this person may move this dashboard between folders.
 *
 * A locked folder is an administrator's to put things into and take them out
 * of -- otherwise anybody could take a dashboard out of the folder protecting
 * it, change it, and put it back. The server refuses it either way; this is so
 * the menu does not offer a button that answers 403.
 */
export function mayMoveFolders({ admin, inLocked, canEdit }) {
  return !!(admin || (!inLocked && canEdit));
}

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
    moveToFolder,
    verify,
    unverify,
  } = dashboardConfiguration;

  const [folders, setFolders] = useState([]);
  useEffect(() => {
    let live_ = true;
    axios
      .get("api/dashboard_folders")
      .then((found) => live_ && setFolders(found || []))
      .catch(() => {});
    return () => {
      live_ = false;
    };
  }, []);

  // A locked folder is an administrator's to put things into and take them out
  // of. Offering the move to anybody else would be offering a button that
  // answers 403 -- the server refuses it either way.
  const admin = currentUser.isAdmin;
  const mayMove = mayMoveFolders({
    admin,
    inLocked: !!(dashboard.folder && dashboard.folder.locked),
    canEdit: dashboard.canEdit(),
  });

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
          {mayMove && (
            <Menu.SubMenu
              key="folder"
              title={
                <span data-test="FolderMenu">
                  {dashboard.folder ? `Folder: ${dashboard.folder.name}` : "File in a folder"}
                </span>
              }
            >
              {folders.map((folder) => (
                <Menu.Item key={`folder-${folder.id}`} disabled={folder.locked && !admin}>
                  <PlainButton onClick={() => moveToFolder(folder.id)}>
                    {dashboard.folder_id === folder.id && <i className="fa fa-check m-r-5" aria-hidden="true" />}
                    {folder.name}
                    {folder.locked && <span className="m-l-5 text-muted">administrators only</span>}
                  </PlainButton>
                </Menu.Item>
              ))}
              {dashboard.folder_id && <Menu.Divider />}
              {dashboard.folder_id && (
                <Menu.Item key="folder-none">
                  <PlainButton onClick={() => moveToFolder(null)}>Take it out</PlainButton>
                </Menu.Item>
              )}
            </Menu.SubMenu>
          )}
          {dashboard.can_verify && (
            <Menu.Item key="verify">
              <PlainButton
                onClick={() =>
                  VerifyDashboardDialog.showModal({ current: dashboard.verification }).onClose((note) => verify(note))
                }
                data-test="VerifyDashboard"
              >
                {dashboard.verification ? "Update verification" : "Verify"}
              </PlainButton>
            </Menu.Item>
          )}
          {dashboard.can_verify && dashboard.verification && (
            <Menu.Item key="unverify">
              <PlainButton onClick={unverify} data-test="UnverifyDashboard">
                Remove verification
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
              {intervalsFor(dashboard).map((interval) => (
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
