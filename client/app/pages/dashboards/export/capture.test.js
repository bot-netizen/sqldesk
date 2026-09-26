import { MAX_WIDGETS, captureScale, foreignImageCount, stripXmlIllegal, tooBigToExport } from "./index";

jest.mock("html-to-image", () => ({ toPng: jest.fn() }));
jest.mock("@sqldesk/viz/lib/services/offscreen", () => ({ revealAllCharts: jest.fn() }));
jest.mock("@/services/auth", () => ({ currentUser: { name: "Test" } }));
jest.mock("@/assets/images/sqldesk_icon.svg", () => "logo.svg", { virtual: true });

/*
  Two ways a dashboard export failed that had nothing to do with the
  dashboard: a canvas too large for Safari to allocate, and a single image
  from another website taking the whole capture down with it.
*/
describe("captureScale", () => {
  const SAFARI_LIMIT = 16777216;

  test("an ordinary dashboard keeps its 2x capture", () => {
    expect(captureScale(1440, 2000)).toBe(2);
  });

  test("a tall one drops below 2x rather than asking for a canvas Safari refuses", () => {
    // The "Every visualization" demo dashboard: 61 million pixels at 2x.
    const scale = captureScale(1440 + 80, 10615 + 144);
    const pixels = (1440 + 80) * scale * (10615 + 144) * scale;

    expect(scale).toBeLessThan(2);
    expect(pixels).toBeLessThanOrEqual(SAFARI_LIMIT);
  });

  test("never so small that the export is unreadable", () => {
    expect(captureScale(1440, 200000)).toBe(0.5);
  });
});

describe("foreignImageCount", () => {
  function grid(html) {
    const element = document.createElement("div");
    element.innerHTML = html;
    return element;
  }

  test("counts images the page cannot copy", () => {
    const element = grid(
      '<img src="https://a.tile.openstreetmap.org/1/0/0.png"><img src="https://example.com/logo.png">'
    );

    expect(foreignImageCount(element)).toBe(2);
  });

  test("leaves out the ones it can: same origin, data: and blob:", () => {
    const element = grid(
      '<img src="/static/images/marker-icon.png">' +
        '<img src="data:image/png;base64,AAAA">' +
        '<img src="blob:http://localhost/1234">'
    );

    expect(foreignImageCount(element)).toBe(0);
  });

  test("an empty src is not an image anyone is missing", () => {
    expect(foreignImageCount(grid("<img>"))).toBe(0);
  });
});

describe("stripXmlIllegal", () => {
  const wrap = (text) => `data:image/svg+xml;charset=utf-8,${encodeURIComponent(`<svg><text>${text}</text></svg>`)}`;

  test("removes a control character XML cannot hold", () => {
    // The sankey's stage separator, which made one widget unexportable.
    const cleaned = stripXmlIllegal(wrap("South\u001f1"));

    expect(decodeURIComponent(cleaned.split(",")[1])).toBe("<svg><text>South1</text></svg>");
  });

  test("keeps tab, newline and carriage return, which XML allows", () => {
    const cleaned = stripXmlIllegal(wrap("a\tb\nc\rd"));

    expect(decodeURIComponent(cleaned.split(",")[1])).toBe("<svg><text>a\tb\nc\rd</text></svg>");
  });

  test("never eats a literal percent sign from somebody's data", () => {
    // "%1F" typed as text is encoded as "%251F", which is not a control char.
    const cleaned = stripXmlIllegal(wrap("100%1F and %0A"));

    expect(decodeURIComponent(cleaned.split(",")[1])).toBe("<svg><text>100%1F and %0A</text></svg>");
  });

  test("removes the two noncharacters as well", () => {
    const cleaned = stripXmlIllegal(wrap("x￾y￿z"));

    expect(decodeURIComponent(cleaned.split(",")[1])).toBe("<svg><text>xyz</text></svg>");
  });
});

describe("tooBigToExport", () => {
  /*
    Export is a one-page report. Past one page, or past a dozen widgets, the
    answer is "too big" at once rather than a long wait for a file nobody
    will read.
  */
  test("a short dashboard of a few charts exports", () => {
    expect(tooBigToExport({ width: 1440, height: 900, widgets: 6 })).toBeNull();
  });

  test("a little over a page still fits, shrunk to one", () => {
    // A4 landscape at 1520px wide is 1074px tall; 1250 + 144 is 1.3 pages.
    expect(tooBigToExport({ width: 1440, height: 1250, widgets: 8 })).toBeNull();
  });

  test("a tall dashboard is too big, and says how many pages it would take", () => {
    // The "Every visualization" demo dashboard.
    const reason = tooBigToExport({ width: 1440, height: 10615, widgets: 10 });
    expect(reason).toMatch(/one-page report/);
    expect(reason).toMatch(/11 pages/);
  });

  test("more widgets than a report holds is too big, however short", () => {
    const reason = tooBigToExport({ width: 1440, height: 600, widgets: MAX_WIDGETS + 1 });
    expect(reason).toMatch(new RegExp(`${MAX_WIDGETS + 1} widgets`));
  });

  test("exactly the limit is allowed", () => {
    expect(tooBigToExport({ width: 1440, height: 600, widgets: MAX_WIDGETS })).toBeNull();
  });
});
