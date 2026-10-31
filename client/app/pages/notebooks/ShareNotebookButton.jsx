import React, { useCallback, useState } from "react";
import PropTypes from "prop-types";
import Button from "antd/lib/button";
import Dropdown from "antd/lib/dropdown";
import Menu from "antd/lib/menu";
import Modal from "antd/lib/modal";
import ShareAltOutlinedIcon from "@ant-design/icons/ShareAltOutlined";
import LinkOutlinedIcon from "@ant-design/icons/LinkOutlined";
import FilePdfOutlinedIcon from "@ant-design/icons/FilePdfOutlined";
import FileImageOutlinedIcon from "@ant-design/icons/FileImageOutlined";
import StopOutlinedIcon from "@ant-design/icons/StopOutlined";
import notification from "@/services/notification";
import Notebook from "@/services/notebook";
import {
  exportSizeProblem,
  renderDashboardToPng,
  renderDashboardToPdf,
  downloadBlob,
  filenameFor,
} from "../dashboards/export";

/*
  The notebook's share surface, deliberately the dashboard's.

  Everything that hands this notebook to somebody else lives behind one
  button -- a link, a PDF, an image -- because that is where people already
  look for it, and two surfaces that do the same job in different shapes is
  the thing that makes a product feel assembled rather than designed.

  The export itself is the dashboard's code unchanged: `renderDashboardToPng`
  and `renderDashboardToPdf` capture whatever element they are given, so a
  notebook hands them its cells and gets back the same file a dashboard
  would. What is captured is the cells, not the page -- no header, no
  navigation, and folded cells stay folded, because a notebook somebody
  tidied is the report they meant to send.
*/
export default function ShareNotebookButton({ notebook, getExportTarget, onChanged }) {
  const [busy, setBusy] = useState(null);

  const runExport = useCallback(
    async (kind, render, extension) => {
      const element = getExportTarget();
      if (!element) {
        notification.error("Nothing to export", "The notebook is still loading.");
        return;
      }
      // Asked before anything starts, and answered where the person is
      // looking -- the two formats have different limits, so it is asked
      // per format rather than once.
      const tooBig = exportSizeProblem(element, kind);
      if (tooBig) {
        Modal.warning({ title: "Too big to export", content: tooBig, okText: "OK" });
        return;
      }
      setBusy(kind);
      try {
        const { blob } = await render(element, { title: notebook.name });
        if (!blob) {
          throw new Error("The notebook could not be captured.");
        }
        downloadBlob(blob, filenameFor(notebook.name, extension));
      } catch (e) {
        notification.error("That export did not finish", (e && e.message) || "Try again.");
      } finally {
        setBusy(null);
      }
    },
    [getExportTarget, notebook]
  );

  const link = useCallback(() => {
    if (notebook.public_url) {
      // Shown rather than silently copied: a link somebody is about to send
      // is a thing they want to see first.
      Modal.confirm({
        title: "Anyone with this link can read this notebook",
        content: notebook.public_url,
        okText: "Copy link",
        cancelText: "Stop sharing",
        onOk: () => {
          navigator.clipboard
            .writeText(notebook.public_url)
            .then(() => notification.success("Link copied."))
            .catch(() => notification.warning("Copy it from the address above."));
        },
        onCancel: () =>
          Notebook.unshare(notebook.id).then(() => {
            notification.success("That link no longer works.");
            onChanged();
          }),
      });
      return;
    }
    Notebook.share(notebook.id)
      .then(() => {
        notification.success("Anyone with the link can now read this notebook.");
        onChanged();
      })
      .catch((reason) => notification.error((reason && reason.message) || "That link could not be made."));
  }, [notebook, onChanged]);

  const menu = (
    <Menu>
      {notebook.can_edit && !notebook.is_draft && (
        <Menu.Item key="link" onClick={link} data-test="ShareLink">
          {notebook.public_url ? <StopOutlinedIcon /> : <LinkOutlinedIcon />}
          <span className="m-l-5">{notebook.public_url ? "Shared — show or stop" : "Copy a public link"}</span>
        </Menu.Item>
      )}
      <Menu.Item
        key="pdf"
        disabled={!!busy}
        onClick={() => runExport("pdf", renderDashboardToPdf, "pdf")}
        data-test="SharePdf"
      >
        <FilePdfOutlinedIcon />
        <span className="m-l-5">{busy === "pdf" ? "Making the PDF…" : "Download as PDF"}</span>
      </Menu.Item>
      <Menu.Item
        key="png"
        disabled={!!busy}
        onClick={() => runExport("png", renderDashboardToPng, "png")}
        data-test="ShareImage"
      >
        <FileImageOutlinedIcon />
        <span className="m-l-5">{busy === "png" ? "Making the image…" : "Download as image"}</span>
      </Menu.Item>
    </Menu>
  );

  return (
    <Dropdown overlay={menu} trigger={["click"]} placement="bottomRight">
      <Button size="small" data-test="ShareNotebook">
        <ShareAltOutlinedIcon /> {notebook.public_url ? "Shared" : "Share"}
      </Button>
    </Dropdown>
  );
}

ShareNotebookButton.propTypes = {
  notebook: PropTypes.object.isRequired,
  getExportTarget: PropTypes.func.isRequired,
  onChanged: PropTypes.func.isRequired,
};
