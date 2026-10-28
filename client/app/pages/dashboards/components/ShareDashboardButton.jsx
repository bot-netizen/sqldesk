import React, { useCallback, useState } from "react";
import PropTypes from "prop-types";
import { get } from "lodash";
import Button from "antd/lib/button";
import Dropdown from "antd/lib/dropdown";
import Menu from "antd/lib/menu";
import Modal from "antd/lib/modal";
import ShareAltOutlinedIcon from "@ant-design/icons/ShareAltOutlined";
import LinkOutlinedIcon from "@ant-design/icons/LinkOutlined";
import FilePdfOutlinedIcon from "@ant-design/icons/FilePdfOutlined";
import FileImageOutlinedIcon from "@ant-design/icons/FileImageOutlined";
import MailOutlinedIcon from "@ant-design/icons/MailOutlined";
import SlackOutlinedIcon from "@ant-design/icons/SlackOutlined";
import PlainButton from "@/components/PlainButton";
import notification from "@/services/notification";
import { currentUser, clientConfig } from "@/services/auth";
import SubscribeDashboardDialog from "./SubscribeDashboardDialog";
import SendToSlackDialog from "./SendToSlackDialog";
import { exportSizeProblem, renderDashboardToPng, renderDashboardToPdf, downloadBlob, filenameFor } from "../export";

/*
  The dashboard's share surface.

  Deliberately its own button rather than another entry in the overflow
  menu: sharing is a primary action, and everything that hands this dashboard
  to somebody else lives here -- a link, a schedule, a Slack channel, a file.

  Export runs against a DOM element the caller supplies, so what gets
  captured is the dashboard grid rather than the whole page — no header,
  no navigation.
*/
export default function ShareDashboardButton({ dashboard, getExportTarget, onShowPublicLink }) {
  const [busy, setBusy] = useState(null);

  const runExport = useCallback(
    async (kind, render, extension) => {
      const element = getExportTarget();
      if (!element) {
        notification.error("Nothing to export", "The dashboard is still loading.");
        return;
      }
      // Asked before anything starts, and answered where the person is
      // looking. As a corner notice after a spinner, the answer took 100ms
      // to arrive and 3s to vanish, and read as the button being broken.
      //
      // Asked per format, because the two have different limits: the PDF is
      // a one-page report and the image is as tall as the dashboard.
      const tooBig = exportSizeProblem(element, kind);
      if (tooBig) {
        Modal.warning({ title: "Too big to export", content: tooBig, okText: "OK" });
        return;
      }
      setBusy(kind);
      try {
        const { blob, skippedImages, failedWidgets } = await render(element);
        if (!blob) {
          throw new Error("The dashboard could not be captured.");
        }
        downloadBlob(blob, filenameFor(dashboard.name, extension));
        // The file is made either way; what the user needs to know is what
        // is missing from it and why, not a vague "something broke".
        const missing = [];
        if (failedWidgets > 0) {
          missing.push(
            `${failedWidgets} widget${failedWidgets === 1 ? " could" : "s could"} not be drawn and ` +
              `${failedWidgets === 1 ? "is" : "are"} marked as a gap.`
          );
        }
        if (skippedImages > 0) {
          missing.push(
            `${skippedImages} image${skippedImages === 1 ? "" : "s"} from other websites — map tiles, pictures in ` +
              "text boxes — cannot be copied by the browser and " +
              `${skippedImages === 1 ? "is" : "are"} blank.`
          );
        }
        if (missing.length > 0) {
          notification.warning(
            "Exported, with something missing",
            `${missing.join(" ")} Everything else is included.`,
            { duration: 10 }
          );
        }
      } catch (error) {
        if (error && error.name === "TooBigToExport") {
          Modal.warning({ title: "Too big to export", content: error.message, okText: "OK" });
          return;
        }
        notification.error(
          `Could not export as ${extension.toUpperCase()}`,
          (error && error.message) || "The dashboard could not be captured.",
          { duration: 10 }
        );
      } finally {
        setBusy(null);
      }
    },
    [dashboard.name, getExportTarget]
  );

  const owner = get(dashboard, "user.name");

  const exportPdf = useCallback(
    () => runExport("pdf", (element) => renderDashboardToPdf(element, { title: dashboard.name, owner }), "pdf"),
    [runExport, dashboard.name, owner]
  );

  const exportImage = useCallback(
    () => runExport("png", (element) => renderDashboardToPng(element, { title: dashboard.name, owner }), "png"),
    [runExport, dashboard.name, owner]
  );

  // Sending needs a renderer, which is a separate optional container, so the
  // feature is only offered where one is configured -- `can` asks both
  // questions. A dashboard nobody has saved yet has nothing to subscribe to.
  const canSubscribe = currentUser.can("send_dashboards") && !dashboard.is_draft;

  const subscribe = useCallback(() => SubscribeDashboardDialog.showModal({ dashboard }), [dashboard]);

  // Same permission as mailing it, and the same reason: both hand the
  // dashboard's contents to people who are not looking at SQLDesk. Offered
  // only where an administrator has connected a workspace, because the dialog's
  // first act is to ask Slack for channels.
  const canSlack = canSubscribe && clientConfig.slackConfigured;

  const sendToSlack = useCallback(() => SendToSlackDialog.showModal({ dashboard }), [dashboard]);

  return (
    <Dropdown
      trigger={["click"]}
      placement="bottomRight"
      overlay={
        <Menu data-test="ShareDashboardMenu">
          {/* Sharing a link and exporting a file are both "give this to
              somebody else", and they used to be two buttons side by side --
              one a dropdown, one an icon -- with no way to tell which was
              which. The link comes first because it is the one that stays up
              to date. */}
          {onShowPublicLink && (
            <Menu.Item key="link">
              <PlainButton onClick={onShowPublicLink} data-test="OpenShareForm">
                <LinkOutlinedIcon className="m-r-5" aria-hidden="true" />
                Public link&hellip;
              </PlainButton>
            </Menu.Item>
          )}
          {canSubscribe && (
            <Menu.Item key="subscribe">
              <PlainButton onClick={subscribe} data-test="SubscribeDashboardButton">
                <MailOutlinedIcon className="m-r-5" aria-hidden="true" />
                Send on a schedule&hellip;
              </PlainButton>
            </Menu.Item>
          )}
          {canSlack && (
            <Menu.Item key="slack">
              <PlainButton onClick={sendToSlack} data-test="SendToSlackButton">
                <SlackOutlinedIcon className="m-r-5" aria-hidden="true" />
                Send to Slack&hellip;
              </PlainButton>
            </Menu.Item>
          )}
          {(onShowPublicLink || canSubscribe || canSlack) && <Menu.Divider />}
          <Menu.Item key="pdf" disabled={!!busy}>
            <PlainButton onClick={exportPdf} data-test="ExportPdfButton">
              <FilePdfOutlinedIcon className="m-r-5" aria-hidden="true" />
              {busy === "pdf" ? "Preparing PDF…" : "Export as PDF"}
            </PlainButton>
          </Menu.Item>
          <Menu.Item key="png" disabled={!!busy}>
            <PlainButton onClick={exportImage} data-test="ExportImageButton">
              <FileImageOutlinedIcon className="m-r-5" aria-hidden="true" />
              {busy === "png" ? "Preparing image…" : "Export as image"}
            </PlainButton>
          </Menu.Item>
        </Menu>
      }
    >
      {/* Words rather than antd's loading icon. An export takes under a second,
          and the icon spent it inside its own entrance animation -- a clipped
          quarter arc that looked broken rather than busy. */}
      <Button className="m-l-5" data-test="ShareDashboardButton" disabled={!!busy} aria-busy={!!busy}>
        <ShareAltOutlinedIcon aria-hidden="true" />
        <span className="m-l-5">{busy ? "Exporting…" : "Share"}</span>
      </Button>
    </Dropdown>
  );
}

ShareDashboardButton.propTypes = {
  // eslint-disable-next-line react/forbid-prop-types
  dashboard: PropTypes.object.isRequired,
  getExportTarget: PropTypes.func.isRequired,
  // Null when this user cannot share the dashboard, which is not the same as
  // the menu having no link item to show.
  onShowPublicLink: PropTypes.func,
};

ShareDashboardButton.defaultProps = {
  onShowPublicLink: null,
};
