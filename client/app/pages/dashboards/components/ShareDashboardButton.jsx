import React, { useCallback, useState } from "react";
import PropTypes from "prop-types";
import { get } from "lodash";
import Button from "antd/lib/button";
import Dropdown from "antd/lib/dropdown";
import Menu from "antd/lib/menu";
import ShareAltOutlinedIcon from "@ant-design/icons/ShareAltOutlined";
import LinkOutlinedIcon from "@ant-design/icons/LinkOutlined";
import FilePdfOutlinedIcon from "@ant-design/icons/FilePdfOutlined";
import FileImageOutlinedIcon from "@ant-design/icons/FileImageOutlined";
import PlainButton from "@/components/PlainButton";
import notification from "@/services/notification";
import { renderDashboardToPng, renderDashboardToPdf, downloadBlob, filenameFor } from "../export";

/*
  The dashboard's share surface.

  Deliberately its own button rather than another entry in the overflow
  menu: sharing is a primary action, and this is where posting a snapshot
  to Slack will live once the server can render a dashboard headlessly.

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
      setBusy(kind);
      try {
        const blob = await render(element);
        if (!blob) {
          throw new Error("The dashboard could not be captured.");
        }
        downloadBlob(blob, filenameFor(dashboard.name, extension));
      } catch (error) {
        // Capture failures are usually a widget the renderer could not read
        // (a cross-origin image, say), which is worth saying rather than
        // failing silently.
        notification.error(`Could not export as ${extension.toUpperCase()}`, error && error.message);
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
          {onShowPublicLink && <Menu.Divider />}
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
      <Button className="m-l-5" data-test="ShareDashboardButton" loading={!!busy}>
        {!busy && <ShareAltOutlinedIcon aria-hidden="true" />}
        <span className="m-l-5">Share</span>
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
