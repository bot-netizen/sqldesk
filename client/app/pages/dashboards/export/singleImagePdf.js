/*
  Builds a PDF wrapping one JPEG per page.

  Written here rather than pulling in jsPDF, which unpacks to ~30MB for what
  amounts to a fixed 5-object document. A PDF holding one image is a small,
  fully specified structure, and keeping it in-tree avoids adding a large
  dependency to a bundle that is already 9.4MB.

  JPEG specifically: DCTDecode takes the encoder's bytes verbatim, so the
  image needs no re-encoding. PNG would mean FlateDecode plus predictor
  handling for no benefit at this size.
*/

const A4_LANDSCAPE = { width: 842, height: 595 };
//: A notebook is read down the page, so it prints down the page. The
//: dashboard's landscape is for a one-page report of charts side by side.
const A4_PORTRAIT = { width: 595, height: 842 };

function toBytes(str) {
  const out = new Uint8Array(str.length);
  for (let i = 0; i < str.length; i += 1) {
    out[i] = str.charCodeAt(i) & 0xff;
  }
  return out;
}

// Fit the capture onto a sane paper size instead of emitting a page as large
// as the screenshot: a 1920px-wide capture would otherwise be a 26-inch page.
//
// `align` is "center" for a single sheet and "top" for a page out of a
// document: the last page of a notebook is usually a short one, and centring
// it would float half a page of cells in the middle of otherwise empty paper
// while every page before it started at the top margin.
export function fitToPage(imageWidth, imageHeight, page = A4_LANDSCAPE, align = "center") {
  const scale = Math.min(page.width / imageWidth, page.height / imageHeight);
  const width = imageWidth * scale;
  const height = imageHeight * scale;
  const slack = Math.max(0, page.height - height);
  return {
    width,
    height,
    // Clamped: an image fitted exactly to the page otherwise comes out a
    // hair wider in floating point and writes "-0.00" into the PDF.
    offsetX: Math.max(0, (page.width - width) / 2),
    // PDF's origin is the bottom-left corner, so "top" is all the slack.
    offsetY: align === "top" ? slack : slack / 2,
    pageWidth: page.width,
    pageHeight: page.height,
  };
}

/*
  A PDF of `pages`, each one a JPEG laid on its own sheet.

  One writer for both callers rather than two. A dashboard is the one-page
  case and a notebook is the many-page case, and the difference between them
  is a loop -- where two writers would be two places for an object offset to
  go wrong, in a file format where a wrong offset is a document that opens
  to nothing with no error.

  Objects: the catalog, the page tree, then three per page (the page, its
  image, its content stream), then the info dictionary last.
*/
export function buildImagePdf({ pages, title, page = A4_LANDSCAPE, align = "center", kind = "Dashboard" }) {
  if (!pages || !pages.length) {
    throw new Error("A PDF needs at least one page.");
  }

  const laid = pages.map((one) => ({
    ...one,
    box: fitToPage(one.imageWidth, one.imageHeight, page, align),
  }));

  const first = 3;
  const pageNumber = (index) => first + index * 3;
  const imageNumber = (index) => first + index * 3 + 1;
  const contentNumber = (index) => first + index * 3 + 2;
  const infoNumber = first + laid.length * 3;

  const kids = laid.map((one, index) => `${pageNumber(index)} 0 R`).join(" ");

  const chunks = [];
  const offsets = [];
  let position = 0;

  const push = (bytes) => {
    chunks.push(bytes);
    position += bytes.length;
  };
  const object = (number, body) => {
    offsets[number] = position;
    push(toBytes(`${number} 0 obj\n${body}\nendobj\n`));
  };

  push(toBytes("%PDF-1.4\n"));
  // A binary comment marks the file as containing binary data, so tools do
  // not mangle it as text.
  push(new Uint8Array([0x25, 0xe2, 0xe3, 0xcf, 0xd3, 0x0a]));

  object(1, "<< /Type /Catalog /Pages 2 0 R >>");
  object(2, `<< /Type /Pages /Kids [${kids}] /Count ${laid.length} >>`);

  laid.forEach((one, index) => {
    const { box } = one;
    const content =
      `q ${box.width.toFixed(2)} 0 0 ${box.height.toFixed(2)} ` +
      `${box.offsetX.toFixed(2)} ${box.offsetY.toFixed(2)} cm /Im0 Do Q\n`;

    object(
      pageNumber(index),
      `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${box.pageWidth} ${box.pageHeight}] ` +
        `/Resources << /XObject << /Im0 ${imageNumber(index)} 0 R >> >> /Contents ${contentNumber(index)} 0 R >>`
    );

    // The image's stream is binary, so it is spliced in rather than built
    // as a string.
    offsets[imageNumber(index)] = position;
    push(
      toBytes(
        `${imageNumber(index)} 0 obj\n<< /Type /XObject /Subtype /Image /Width ${one.imageWidth} ` +
          `/Height ${one.imageHeight} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode ` +
          `/Length ${one.jpegBytes.length} >>\nstream\n`
      )
    );
    push(one.jpegBytes);
    push(toBytes("\nendstream\nendobj\n"));

    object(contentNumber(index), `<< /Length ${content.length} >>\nstream\n${content}endstream`);
  });

  object(infoNumber, `<< /Title (${String(title || kind).replace(/([()\\])/g, "\\$1")}) >>`);

  const xrefOffset = position;
  const count = infoNumber + 1;
  let xref = `xref\n0 ${count}\n0000000000 65535 f \n`;
  for (let i = 1; i < count; i += 1) {
    xref += `${String(offsets[i]).padStart(10, "0")} 00000 n \n`;
  }
  xref += `trailer\n<< /Size ${count} /Root 1 0 R /Info ${infoNumber} 0 R >>\nstartxref\n${xrefOffset}\n%%EOF\n`;
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

// The one-page case, which is what a dashboard export is.
export default function buildSingleImagePdf({ jpegBytes, imageWidth, imageHeight, title }) {
  return buildImagePdf({ pages: [{ jpegBytes, imageWidth, imageHeight }], title });
}

export { A4_LANDSCAPE, A4_PORTRAIT };
