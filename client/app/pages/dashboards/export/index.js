import { getFontEmbedCSS, toSvg } from "html-to-image";
import { revealAllCharts } from "@sqldesk/viz/lib/services/offscreen";
import { A4_LANDSCAPE, buildImagePdf, paginate } from "./imagePdf";
import composeExportCanvas, { PAGE_FURNITURE } from "./compose";
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

/*
  The largest canvas every browser we support will actually allocate.

  Safari refuses a canvas over about 16.7 million pixels -- silently, with a
  blank result -- and Chrome's limit is far higher, so Safari is the one that
  decides. A tall dashboard at 2x crosses it easily: 1440 x 10,600 CSS pixels
  is 61 million at 2x. Such a capture drops towards 1x rather than failing,
  which is still sharp enough to read, and ordinary dashboards keep their 2x.
*/
const MAX_CANVAS_PIXELS = 16000000;

export function captureScale(width, height) {
  const area = Math.max(1, width) * Math.max(1, height);
  const fits = Math.sqrt(MAX_CANVAS_PIXELS / area);
  return Math.max(0.5, Math.min(CAPTURE_SCALE, fits));
}

/*
  What an image the browser will not let us copy turns into.

  html-to-image re-fetches every <img> to inline it. The app's CSP allows
  fetch() only to its own origin, so a map tile or a picture in a textbox
  from another site cannot be read -- and the library then sets that image's
  src to "", its onerror fires, and it rejects the *whole* capture with a
  bare Event. That was "Could not export as PNG" with no explanation, on any
  dashboard with a map on it. A transparent pixel keeps the export going;
  the caller is told how many images were left out.
*/
const TRANSPARENT_PIXEL =
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=";

/*
  Images from another origin, which the capture cannot copy.

  Counted after the charts are revealed rather than before: revealing
  resizes a map, and Leaflet answers a resize by requesting its tiles again,
  so the tiles on the page just before capture are not the ones that were
  there when the button was pressed.
*/
export function foreignImageCount(element) {
  return Array.from(element.querySelectorAll("img, image")).filter((node) => {
    const src = node.getAttribute("src") || node.getAttribute("href") || node.getAttribute("xlink:href") || "";
    if (!src || src.startsWith("data:") || src.startsWith("blob:")) {
      return false;
    }
    try {
      return new URL(src, window.location.href).origin !== window.location.origin;
    } catch (error) {
      return false;
    }
  }).length;
}

// Controls belong to the app, not the dashboard being shared.
function isAppControl(node) {
  return !!(node.classList && node.classList.contains("widget-menu-regular"));
}

/*
  Characters XML 1.0 forbids, as encodeURIComponent writes them: C0 controls
  other than tab, newline and carriage return, and U+FFFE/U+FFFF.

  HTML holds them without complaint -- a chart's generated aria-label, a
  control character in a table cell from somebody's data -- and XML does
  not. One of them anywhere in a widget makes that widget's whole SVG
  unparseable, which the browser reports as an image that failed to load,
  with no reason attached. The sankey's stage separator was exactly this.
  A literal "%" in the data is written as "%25", so this cannot eat text.
*/
const XML_ILLEGAL = /%(?:0[0-8BCEF]|1[0-9A-F])|%EF%BF%B[EF]/gi;

export function stripXmlIllegal(svgDataUrl) {
  return svgDataUrl.replace(XML_ILLEGAL, "");
}

// Our own loader rather than the library's: this one says what failed, and
// does not wait on an animation frame, which a background tab never gets.
function loadSvg(url) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("The widget's image could not be read."));
    image.src = url;
  });
}

function tileOptions(fontEmbedCSS, width, height) {
  return {
    width,
    height,
    fontEmbedCSS,
    imagePlaceholder: TRANSPARENT_PIXEL,
    // Belt and braces: anything that still fails to load resolves rather
    // than taking the widget down with it.
    onImageErrorHandler: () => undefined,
    // A grid item is placed by a transform. Drawn on its own it belongs at
    // the origin of its own image, not 900px down it.
    style: { transform: "none", top: "0", left: "0", margin: "0" },
    filter: (node) => !isAppControl(node),
  };
}

function surfaceColor() {
  const value = getComputedStyle(document.documentElement).getPropertyValue("--color-canvas").trim();
  return value || "#ffffff";
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

/*
  Charts below the fold have not been built yet -- they wait for the viewport,
  which is the right answer for reading and the wrong one for a capture of a
  document taller than the window. Waking them is instant; drawing them is
  not, so this then waits for the chart that takes longest to settle.

  250ms covers the two frames ECharts' lazy update takes plus viz-lib's
  resize watcher, which polls at 100ms and is what tells a chart the size of
  the box it was just put in.
*/
const DRAW_SETTLE_MS = 250;

function drawEverything() {
  revealAllCharts();
  return new Promise((resolve) => setTimeout(resolve, DRAW_SETTLE_MS));
}

// A library that rejects with an Event, or a string, would otherwise reach
// the user as an error notice with nothing written in it.
function asError(error, fallback) {
  if (error instanceof Error && error.message) {
    return error;
  }
  return new Error(fallback);
}

/*
  A widget that could not be drawn: a labelled gap where it would have been,
  so the rest of the page still reads and the reader can see something is
  missing rather than wondering whether the dashboard had a hole in it.
*/
function drawGap(context, x, y, width, height, scale) {
  context.save();
  context.fillStyle = "#f1efec";
  context.fillRect(x, y, width, height);
  context.strokeStyle = "#d8d3cb";
  context.lineWidth = scale;
  context.setLineDash([6 * scale, 4 * scale]);
  context.strokeRect(x + scale / 2, y + scale / 2, width - scale, height - scale);
  context.fillStyle = "#6f6b66";
  context.font = `500 ${12 * scale}px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`;
  context.textAlign = "center";
  context.textBaseline = "middle";
  context.fillText("This widget could not be drawn", x + width / 2, y + height / 2);
  context.restore();
}

/*
  One widget at a time, stitched onto one canvas.

  Capturing the whole grid at once serialises every element with every
  computed style into a single SVG. The 80-widget demo dashboard came to
  55 MB -- 40 of it copied CSS, 11 of it fonts -- and the browser refuses to
  decode an image that size, so the export failed with nothing to say why.
  Per widget, each image is a small fraction of that, the export's memory is
  bounded by its largest widget rather than by the dashboard, and a widget
  that cannot be drawn becomes a labelled gap instead of the reason there is
  no file at all.
*/
async function captureGrid(container, { scale, background }) {
  const box = container.getBoundingClientRect();
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(container.scrollWidth * scale);
  canvas.height = Math.round(container.scrollHeight * scale);
  const context = canvas.getContext("2d");
  context.fillStyle = background;
  context.fillRect(0, 0, canvas.width, canvas.height);

  // Fonts once for every widget, and in one format: by default the library
  // embeds every format a stylesheet lists, which for the two icon fonts is
  // five copies of each.
  const fontEmbedCSS = await getFontEmbedCSS(container, { preferredFontFormat: "woff2" });

  const items = Array.from(container.querySelectorAll(".react-grid-item"));
  let failedWidgets = 0;

  // Heights a page may be cut at: the foot of each widget, unless another
  // widget spans across it. A PDF cut there never splits a chart in half.
  const spans = items.map((item) => {
    const rect = item.getBoundingClientRect();
    return [(rect.top - box.top) * scale, (rect.bottom - box.top) * scale];
  });
  const breaks = spans
    .map(([, bottom]) => bottom)
    .filter((y) => !spans.some(([top, bottom]) => top < y - 1 && bottom > y + 1));

  for (const item of items) {
    const rect = item.getBoundingClientRect();
    if (rect.width < 1 || rect.height < 1) {
      continue;
    }
    const x = (rect.left - box.left) * scale;
    const y = (rect.top - box.top) * scale;
    try {
      // eslint-disable-next-line no-await-in-loop -- one at a time is the point
      const svg = await withTimeout(
        toSvg(item, tileOptions(fontEmbedCSS, rect.width, rect.height)),
        20000,
        "Drawing a widget"
      );
      // eslint-disable-next-line no-await-in-loop
      const image = await withTimeout(loadSvg(stripXmlIllegal(svg)), 20000, "Reading a widget");
      // Drawn at the export's scale: the browser rasterises an SVG at the
      // size it is drawn, so text stays sharp at 2x.
      context.drawImage(image, x, y, rect.width * scale, rect.height * scale);
    } catch (error) {
      // The drawing step waits for an animation frame, which a browser does
      // not give a tab in the background -- so every remaining widget would
      // time out in turn. Say what to do instead of running that out. Only
      // for a timeout, though: a widget that fails outright is a gap, whether
      // or not the tab happens to be in front.
      const timedOut = error instanceof Error && /timed out/.test(error.message);
      if (timedOut && document.visibilityState === "hidden") {
        throw new Error("Keep this tab open until the export finishes.");
      }
      failedWidgets += 1;
      // Which one, and why -- the notice tells the user a gap exists, this
      // tells whoever has to fix it which widget left it.
      const widget = item.querySelector("[data-test^='WidgetId']");
      // eslint-disable-next-line no-console
      console.warn(
        "Export: a widget could not be drawn",
        widget ? widget.getAttribute("data-test") : item.getAttribute("data-grid") || "unknown",
        error
      );
      drawGap(context, x, y, rect.width * scale, rect.height * scale, scale);
    }
  }

  return { canvas, failedWidgets, breaks };
}

// Capture once, then lay it onto the branded page. Both exports share this
// so a PDF and an image of the same dashboard are the same artefact.
async function capturePage(element, { title, owner }) {
  await withTimeout(drawEverything(), 15000, "Drawing the widgets");
  const skippedImages = foreignImageCount(element);
  // Sized for the finished page, header and margins included: those are
  // drawn after the capture at the same scale, and a capture sized exactly
  // to the limit would be pushed over it by them.
  const scale = captureScale(element.scrollWidth + PAGE_FURNITURE.width, element.scrollHeight + PAGE_FURNITURE.height);

  let grid;
  try {
    grid = await captureGrid(element, { scale, background: surfaceColor() });
  } catch (error) {
    throw asError(error, "The dashboard could not be captured.");
  }

  const canvas = await withTimeout(
    composeExportCanvas({
      dashboardImage: grid.canvas,
      title: capitalizeFirst(title),
      owner,
      generatedBy: currentUser.name,
      // The export is a point-in-time copy, so when it was taken is the
      // difference between current data and something stale in a channel.
      generatedAt: formatDateTime(new Date()),
      scale,
    }),
    15000,
    "Composing the page"
  );
  // The grid sits below the header on the finished page.
  const top = PAGE_FURNITURE.top * scale;
  const breaks = grid.breaks.map((y) => y + top);
  return { canvas, skippedImages, failedWidgets: grid.failedWidgets, breaks };
}

/*
  Both renderers resolve to { blob, skippedImages, failedWidgets }: the file,
  and what is missing from it, so the caller can say so rather than hand over
  a map with no map on it and no explanation.
*/
export async function renderDashboardToPng(element, { title, owner } = {}) {
  const { canvas, skippedImages, failedWidgets } = await capturePage(element, { title, owner });
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
  return { blob, skippedImages, failedWidgets };
}

function jpegBytesOf(canvas) {
  // JPEG rather than PNG: DCTDecode embeds the encoder's bytes verbatim, so
  // the PDF needs no re-encoding step.
  const dataUrl = canvas.toDataURL("image/jpeg", 0.92);
  // A canvas the browser would not allocate encodes as "data:," -- which
  // would otherwise become a PDF that opens to nothing, with no error.
  if (dataUrl.length < 32) {
    throw new Error("The page was too large to encode.");
  }
  const binary = atob(dataUrl.slice(dataUrl.indexOf(",") + 1));
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

export async function renderDashboardToPdf(element, { title, owner } = {}) {
  const { canvas, skippedImages, failedWidgets, breaks } = await capturePage(element, { title, owner });

  // Pages at the width of the capture, as tall as A4 landscape allows at that
  // width, cut between widgets rather than through them.
  const pageHeight = canvas.width * (A4_LANDSCAPE.height / A4_LANDSCAPE.width);
  const pages = paginate(canvas.height, pageHeight, breaks).map(([top, bottom]) => {
    const height = Math.max(1, Math.round(bottom - top));
    const slice = document.createElement("canvas");
    slice.width = canvas.width;
    slice.height = height;
    slice.getContext("2d").drawImage(canvas, 0, top, canvas.width, height, 0, 0, canvas.width, height);
    return { jpegBytes: jpegBytesOf(slice), imageWidth: slice.width, imageHeight: slice.height };
  });

  const pdf = buildImagePdf({ pages, title });
  return { blob: new Blob([pdf], { type: "application/pdf" }), skippedImages, failedWidgets };
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
