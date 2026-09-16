import buildSingleImagePdf, { fitToPage } from "./singleImagePdf";

// A byte sequence standing in for JPEG data, including bytes that would break
// a string-based assembler (nulls, high bytes, and a literal "endstream").
const fakeJpeg = new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10, 0x4a, 0x46, 0x49, 0x46, 0xff, 0xd9]);

function asLatin1(bytes) {
  let s = "";
  bytes.forEach(b => {
    s += String.fromCharCode(b);
  });
  return s;
}

describe("fitToPage", () => {
  test("scales a wide capture down to the page and centres it", () => {
    const box = fitToPage(1920, 1080);
    expect(box.width).toBeCloseTo(842, 0);
    expect(box.height).toBeCloseTo(473.6, 1);
    expect(box.offsetX).toBeCloseTo(0, 5);
    expect(box.offsetY).toBeGreaterThan(0);
  });

  test("scales a tall capture by height instead", () => {
    const box = fitToPage(400, 2000);
    expect(box.height).toBeCloseTo(595, 0);
    expect(box.offsetX).toBeGreaterThan(0);
  });

  test("preserves aspect ratio", () => {
    const box = fitToPage(1600, 900);
    expect(box.width / box.height).toBeCloseTo(1600 / 900, 3);
  });
});

describe("buildSingleImagePdf", () => {
  const pdf = buildSingleImagePdf({
    jpegBytes: fakeJpeg,
    imageWidth: 1920,
    imageHeight: 1080,
    title: "Revenue overview",
  });
  const text = asLatin1(pdf);

  test("starts with a PDF header and ends with EOF", () => {
    expect(text.startsWith("%PDF-1.4")).toBe(true);
    expect(text.trimEnd().endsWith("%%EOF")).toBe(true);
  });

  test("embeds the image bytes verbatim", () => {
    const needle = asLatin1(fakeJpeg);
    expect(text).toContain(needle);
    expect(text).toContain(`/Length ${fakeJpeg.length}`);
  });

  test("declares every object it writes", () => {
    [1, 2, 3, 4, 5, 6].forEach(n => expect(text).toContain(`${n} 0 obj`));
    expect(text).toContain("/Size 7");
  });

  // The offsets are the part that silently corrupts a PDF: a reader follows
  // startxref, then each xref entry, and a byte that is off by one makes the
  // file unopenable while still looking plausible.
  test("startxref points at the xref table", () => {
    const startxref = parseInt(text.slice(text.lastIndexOf("startxref") + 9).trim(), 10);
    expect(text.slice(startxref, startxref + 4)).toBe("xref");
  });

  test("every xref offset lands on its object header", () => {
    const startxref = parseInt(text.slice(text.lastIndexOf("startxref") + 9), 10);
    const table = text.slice(startxref);
    const entries = table.match(/^(\d{10}) 00000 n $/gm);
    expect(entries).toHaveLength(6);
    entries.forEach((entry, i) => {
      const offset = parseInt(entry.slice(0, 10), 10);
      expect(text.slice(offset, offset + `${i + 1} 0 obj`.length)).toBe(`${i + 1} 0 obj`);
    });
  });

  test("escapes parentheses in the title so the dictionary stays valid", () => {
    const withParens = buildSingleImagePdf({
      jpegBytes: fakeJpeg,
      imageWidth: 100,
      imageHeight: 100,
      title: "Q3 (final) \\ draft",
    });
    expect(asLatin1(withParens)).toContain("(Q3 \\(final\\) \\\\ draft)");
  });
});
