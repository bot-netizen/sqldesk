/*
  Builds a PDF of one or more pages, each wrapping a single JPEG.

  Written here rather than pulling in jsPDF, which unpacks to ~30MB for what
  amounts to a fixed 5-object document. A PDF holding one image is a small,
  fully specified structure, and keeping it in-tree avoids adding a large
  dependency to a bundle that is already 9.4MB.

  JPEG specifically: DCTDecode takes the encoder's bytes verbatim, so the
  image needs no re-encoding. PNG would mean FlateDecode plus predictor
  handling for no benefit at this size.
*/

const A4_LANDSCAPE = { width: 842, height: 595 };

function toBytes(str) {
  const out = new Uint8Array(str.length);
  for (let i = 0; i < str.length; i += 1) {
    out[i] = str.charCodeAt(i) & 0xff;
  }
  return out;
}

// Fit the capture onto a sane paper size instead of emitting a page as large
// as the screenshot: a 1920px-wide capture would otherwise be a 26-inch page.
export function fitToPage(imageWidth, imageHeight, page = A4_LANDSCAPE) {
  const scale = Math.min(page.width / imageWidth, page.height / imageHeight);
  const width = imageWidth * scale;
  const height = imageHeight * scale;
  return {
    width,
    height,
    // Clamped: an image fitted exactly to the page otherwise comes out a
    // hair wider in floating point and writes "-0.00" into the PDF.
    offsetX: Math.max(0, (page.width - width) / 2),
    offsetY: Math.max(0, (page.height - height) / 2),
    pageWidth: page.width,
    pageHeight: page.height,
  };
}

/*
  Where to cut a tall capture into pages.

  `breaks` are the heights no widget crosses; cutting at one keeps every
  widget whole on its page. The latest break that fits is taken, but never
  one so early that most of the page would be blank -- and a widget taller
  than a whole page has to be cut somewhere, so then the page is cut where it
  ends. Returns [top, bottom] pairs covering the whole height.

  Without this a dashboard 10,000 pixels tall was shrunk onto one A4 page:
  an 83-point-wide ribbon that nobody could read.
*/
// How much taller than a page the last stretch may be and still go on one
// page, shrunk to fit. A dashboard 5% taller than a page split into a full
// page and a 250-pixel sliver, which reads worse than text at 95%.
const LAST_PAGE_STRETCH = 1.3;

export function paginate(totalHeight, pageHeight, breaks = []) {
  const sorted = [...breaks].sort((a, b) => a - b);
  const cuts = [];
  let top = 0;
  while (totalHeight - top > 1) {
    const limit = top + pageHeight;
    if (totalHeight - top <= pageHeight * LAST_PAGE_STRETCH) {
      cuts.push([top, totalHeight]);
      break;
    }
    const earliest = top + pageHeight * 0.4;
    const fitting = sorted.filter((y) => y > earliest && y <= limit);
    const end = fitting.length > 0 ? fitting[fitting.length - 1] : limit;
    cuts.push([top, end]);
    top = end;
  }
  return cuts;
}

function pdfString(value) {
  return String(value).replace(/([()\\])/g, "\\$1");
}

/*
  pages: [{ jpegBytes, imageWidth, imageHeight }]. One page fits its image
  and centres it, as a single-page export always has; several pages are the
  slices of one tall capture, so each is fitted to the width and set at the
  top, where the next slice's content continues from.
*/
export function buildImagePdf({ pages, title }) {
  const count = pages.length;
  const pageObject = (i) => 3 + 3 * i;
  const imageObject = (i) => 4 + 3 * i;
  const contentObject = (i) => 5 + 3 * i;
  const infoObject = 3 + 3 * count;

  const bodies = {};
  const images = {};
  bodies[1] = "<< /Type /Catalog /Pages 2 0 R >>";
  bodies[2] = `<< /Type /Pages /Kids [${pages.map((_, i) => `${pageObject(i)} 0 R`).join(" ")}] /Count ${count} >>`;

  pages.forEach((page, i) => {
    const box = fitToPage(page.imageWidth, page.imageHeight);
    const offsetY = count > 1 ? box.pageHeight - box.height : box.offsetY;
    const content =
      `q ${box.width.toFixed(2)} 0 0 ${box.height.toFixed(2)} ` +
      `${box.offsetX.toFixed(2)} ${offsetY.toFixed(2)} cm /Im0 Do Q\n`;

    bodies[pageObject(i)] =
      `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${box.pageWidth} ${box.pageHeight}] ` +
      `/Resources << /XObject << /Im0 ${imageObject(i)} 0 R >> >> /Contents ${contentObject(i)} 0 R >>`;
    images[imageObject(i)] = page;
    bodies[contentObject(i)] = `<< /Length ${content.length} >>\nstream\n${content}endstream`;
  });
  bodies[infoObject] = `<< /Title (${pdfString(title || "Dashboard")}) >>`;

  const chunks = [];
  const offsets = [];
  let position = 0;
  const push = (bytes) => {
    chunks.push(bytes);
    position += bytes.length;
  };

  push(toBytes("%PDF-1.4\n"));
  // A binary comment marks the file as containing binary data, so tools do
  // not mangle it as text.
  push(new Uint8Array([0x25, 0xe2, 0xe3, 0xcf, 0xd3, 0x0a]));

  for (let number = 1; number <= infoObject; number += 1) {
    offsets[number] = position;
    const image = images[number];
    if (image) {
      push(
        toBytes(
          `${number} 0 obj\n<< /Type /XObject /Subtype /Image /Width ${image.imageWidth} ` +
            `/Height ${image.imageHeight} /ColorSpace /DeviceRGB /BitsPerComponent 8 ` +
            `/Filter /DCTDecode /Length ${image.jpegBytes.length} >>\nstream\n`
        )
      );
      push(image.jpegBytes);
      push(toBytes("\nendstream\nendobj\n"));
    } else {
      push(toBytes(`${number} 0 obj\n${bodies[number]}\nendobj\n`));
    }
  }

  const xrefOffset = position;
  const size = infoObject + 1;
  let xref = `xref\n0 ${size}\n0000000000 65535 f \n`;
  for (let i = 1; i < size; i += 1) {
    xref += `${String(offsets[i]).padStart(10, "0")} 00000 n \n`;
  }
  xref += `trailer\n<< /Size ${size} /Root 1 0 R /Info ${infoObject} 0 R >>\nstartxref\n${xrefOffset}\n%%EOF\n`;
  push(toBytes(xref));

  const total = chunks.reduce((sum, c) => sum + c.length, 0);
  const pdf = new Uint8Array(total);
  let at = 0;
  chunks.forEach((c) => {
    pdf.set(c, at);
    at += c.length;
  });
  return pdf;
}

// A single image on a single page -- the shape every short dashboard takes.
export default function buildSingleImagePdf({ jpegBytes, imageWidth, imageHeight, title }) {
  return buildImagePdf({ pages: [{ jpegBytes, imageWidth, imageHeight }], title });
}

export { A4_LANDSCAPE };
