/*
  Builds a one-page PDF wrapping a single JPEG.

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

export default function buildSingleImagePdf({ jpegBytes, imageWidth, imageHeight, title }) {
  const box = fitToPage(imageWidth, imageHeight);

  const content =
    `q ${box.width.toFixed(2)} 0 0 ${box.height.toFixed(2)} ` +
    `${box.offsetX.toFixed(2)} ${box.offsetY.toFixed(2)} cm /Im0 Do Q\n`;

  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${box.pageWidth} ${box.pageHeight}] ` +
      "/Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>",
    // object 4 is the image; its stream is binary and spliced in below
    null,
    `<< /Length ${content.length} >>\nstream\n${content}endstream`,
    `<< /Title (${String(title || "Dashboard").replace(/([()\\])/g, "\\$1")}) >>`,
  ];

  const imageDict =
    `<< /Type /XObject /Subtype /Image /Width ${imageWidth} /Height ${imageHeight} ` +
    `/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${jpegBytes.length} >>\nstream\n`;

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

  objects.forEach((body, index) => {
    const number = index + 1;
    offsets[number] = position;
    if (number === 4) {
      push(toBytes(`4 0 obj\n${imageDict}`));
      push(jpegBytes);
      push(toBytes("\nendstream\nendobj\n"));
    } else {
      push(toBytes(`${number} 0 obj\n${body}\nendobj\n`));
    }
  });

  const xrefOffset = position;
  const count = objects.length + 1;
  let xref = `xref\n0 ${count}\n0000000000 65535 f \n`;
  for (let i = 1; i < count; i += 1) {
    xref += `${String(offsets[i]).padStart(10, "0")} 00000 n \n`;
  }
  xref += `trailer\n<< /Size ${count} /Root 1 0 R /Info 6 0 R >>\nstartxref\n${xrefOffset}\n%%EOF\n`;
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

export { A4_LANDSCAPE };
