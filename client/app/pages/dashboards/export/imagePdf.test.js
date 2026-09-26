import buildSingleImagePdf, { buildImagePdf, fitToPage, paginate } from "./imagePdf";

// A byte sequence standing in for JPEG data, including bytes that would break
// a string-based assembler (nulls, high bytes, and a literal "endstream").
const fakeJpeg = new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10, 0x4a, 0x46, 0x49, 0x46, 0xff, 0xd9]);

function asLatin1(bytes) {
  let s = "";
  bytes.forEach((b) => {
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
    [1, 2, 3, 4, 5, 6].forEach((n) => expect(text).toContain(`${n} 0 obj`));
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

describe("paginate", () => {
  test("a capture shorter than a page is one page", () => {
    expect(paginate(500, 800, [])).toEqual([[0, 500]]);
  });

  test("a tall capture is cut at the latest break that fits", () => {
    // Widgets end at 300, 700 and 1100; a page is 800 tall.
    expect(paginate(1500, 800, [300, 700, 1100])).toEqual([
      [0, 700],
      [700, 1500],
    ]);
  });

  test("a break so early the page would be mostly blank is passed over", () => {
    // The only break is at 100 of an 800 page: cut at the page instead.
    expect(paginate(2000, 800, [100])).toEqual([
      [0, 800],
      [800, 1600],
      [1600, 2000],
    ]);
  });

  test("the pages cover the whole height with no gap and no overlap", () => {
    const cuts = paginate(10721, 1054, [900, 1500, 2100, 2900, 4100, 5000, 6200, 7400, 8800, 9900]);

    expect(cuts[0][0]).toBe(0);
    expect(cuts[cuts.length - 1][1]).toBe(10721);
    cuts.slice(1).forEach(([top], i) => expect(top).toBe(cuts[i][1]));
    // Every page but the last fits; the last may stretch a little rather
    // than leave a sliver.
    cuts.slice(0, -1).forEach(([top, bottom]) => expect(bottom - top).toBeLessThanOrEqual(1054));
    const [lastTop, lastBottom] = cuts[cuts.length - 1];
    expect(lastBottom - lastTop).toBeLessThanOrEqual(1054 * 1.3);
  });

  test("a capture a little taller than a page stays on one page", () => {
    // The small demo dashboard was 1.05 pages and split off a 250px sliver.
    expect(paginate(2228, 2127, [1978])).toEqual([[0, 2228]]);
  });

  test("the last page never ends as a sliver", () => {
    const cuts = paginate(2150, 1000, [900, 1950]);
    const [lastTop, lastBottom] = cuts[cuts.length - 1];

    expect(lastBottom - lastTop).toBeGreaterThan(300);
  });
});

describe("buildImagePdf with several pages", () => {
  const jpeg = new Uint8Array([0xff, 0xd8, 0xff, 0xd9]);
  const pages = [
    { jpegBytes: jpeg, imageWidth: 1492, imageHeight: 1054 },
    { jpegBytes: jpeg, imageWidth: 1492, imageHeight: 1054 },
    { jpegBytes: jpeg, imageWidth: 1492, imageHeight: 400 },
  ];
  const text = () => Array.from(buildImagePdf({ pages, title: "Tall" }), (b) => String.fromCharCode(b)).join("");

  test("declares as many pages as it was given", () => {
    expect(text()).toContain("/Count 3");
    expect((text().match(/\/Type \/Page /g) || []).length).toBe(3);
  });

  test("every xref offset still lands on its object header", () => {
    const pdf = text();
    const xref = pdf.slice(pdf.indexOf("xref\n"));
    const offsets = xref
      .split("\n")
      .slice(3)
      .filter((line) => / 00000 n $/.test(line))
      .map((line) => parseInt(line.slice(0, 10), 10));

    offsets.forEach((offset, i) => {
      expect(pdf.slice(offset, offset + `${i + 1} 0 obj`.length)).toBe(`${i + 1} 0 obj`);
    });
  });

  test("slices sit at the top of their page, so the next one continues from there", () => {
    // Page 3 holds a short slice; it should not float in the middle.
    const pdf = text();
    const streams = pdf.match(/q [\d.]+ 0 0 [\d.]+ -?[\d.]+ -?[\d.]+ cm/g);
    const lastY = parseFloat(streams[2].split(" ")[6]);
    const lastHeight = parseFloat(streams[2].split(" ")[4]);

    expect(lastY + lastHeight).toBeCloseTo(595, 0);
  });
});
