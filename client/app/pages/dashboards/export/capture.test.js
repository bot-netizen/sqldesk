import { captureScale, foreignImageCount, stripXmlIllegal } from "./index";

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
