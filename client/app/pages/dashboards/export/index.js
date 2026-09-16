import { toPng } from "html-to-image";
import buildSingleImagePdf from "./singleImagePdf";
import composeExportCanvas from "./compose";
import { capitalizeFirst, formatDateTime } from "@/lib/utils";
import { currentUser } from "@/services/auth";

/*
  Dashboard export.

  Renderers return a Blob rather than triggering a download themselves. That
  separation is the point: today the caller downloads it, and a future
  "send to Slack" posts the same Blob to an endpoint instead. Nothing about
  producing the artefact has to change for that.

  Note for the Slack case specifically: a SCHEDULED post has no browser, so
  it cannot reuse this path at all — it needs the dashboard rendered
  server-side. What this shares with that future work is the shape of the
  result (an image blob and a PDF wrapping it), not the mechanism.
*/

// Captures are taken at 2x so text in the exported image is not soft on
// high-DPI screens, and so a PDF scaled down to A4 still has detail.
const CAPTURE_SCALE = 2;

function captureOptions(element, backgroundColor) {
  return {
    backgroundColor,
    pixelRatio: CAPTURE_SCALE,
    // The capture is of the dashboard grid, whose scroll height exceeds its
    // visible box; without this only the visible part is drawn.
    width: element.scrollWidth,
    height: element.scrollHeight,
    style: { transform: "none", transformOrigin: "top left" },
    // Controls belong to the app, not the dashboard being shared.
    filter: (node) => !(node.classList && node.classList.contains("widget-menu-regular")),
  };
}

function surfaceColor() {
  const value = getComputedStyle(document.documentElement).getPropertyValue("--color-canvas").trim();
  return value || "#ffffff";
}

function loadImage(src) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("The dashboard could not be captured."));
    image.src = src;
  });
}

// An export that never settles leaves the menu saying "Preparing…" forever,
// which is worse than an error: the user has nothing to act on. Every step
// is bounded so a stall surfaces as a failure they can retry.
function withTimeout(promise, ms, what) {
  let timer;
  return Promise.race([
    promise.finally(() => clearTimeout(timer)),
    new Promise((resolve, reject) => {
      timer = setTimeout(() => reject(new Error(`${what} timed out after ${ms / 1000}s.`)), ms);
    }),
  ]);
}

// Capture once, then lay it onto the branded page. Both exports share this
// so a PDF and an image of the same dashboard are the same artefact.
async function capturePage(element, { title, owner }) {
  const dataUrl = await withTimeout(
    toPng(element, captureOptions(element, surfaceColor())),
    30000,
    "Capturing the dashboard"
  );
  const dashboardImage = await withTimeout(loadImage(dataUrl), 15000, "Reading the capture");
  return withTimeout(
    composeExportCanvas({
      dashboardImage,
      title: capitalizeFirst(title),
      owner,
      generatedBy: currentUser.name,
      // The export is a point-in-time copy, so when it was taken is the
      // difference between current data and something stale in a channel.
      generatedAt: formatDateTime(new Date()),
      scale: CAPTURE_SCALE,
    }),
    15000,
    "Composing the page"
  );
}

export async function renderDashboardToPng(element, { title, owner } = {}) {
  const canvas = await capturePage(element, { title, owner });
  return new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
}

export async function renderDashboardToPdf(element, { title, owner } = {}) {
  const canvas = await capturePage(element, { title, owner });

  // JPEG rather than PNG: DCTDecode embeds the encoder's bytes verbatim, so
  // the PDF needs no re-encoding step.
  const dataUrl = canvas.toDataURL("image/jpeg", 0.92);
  const binary = atob(dataUrl.slice(dataUrl.indexOf(",") + 1));
  const jpegBytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    jpegBytes[i] = binary.charCodeAt(i);
  }

  const pdf = buildSingleImagePdf({
    jpegBytes,
    imageWidth: canvas.width,
    imageHeight: canvas.height,
    title,
  });
  return new Blob([pdf], { type: "application/pdf" });
}

export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  // Revoking immediately can cancel the download in some browsers; one tick
  // is enough for the click to have been handled.
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// Filenames come from user-supplied dashboard names, so strip anything that
// is awkward in a filename rather than trusting the name.
export function filenameFor(name, extension) {
  const safe = String(name || "dashboard")
    .replace(/[^\w\s-]/g, "")
    .trim()
    .replace(/\s+/g, "-")
    .toLowerCase()
    .slice(0, 80);
  const stamp = new Date().toISOString().slice(0, 10);
  return `${safe || "dashboard"}-${stamp}.${extension}`;
}
