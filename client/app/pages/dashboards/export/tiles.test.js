import { NOTEBOOK_TILES, DASHBOARD_TILES, renderDashboardToPng } from "./index";

jest.mock("html-to-image", () => ({
  toSvg: jest.fn(() => Promise.resolve("data:image/svg+xml,<svg/>")),
  getFontEmbedCSS: jest.fn(() => Promise.resolve("")),
}));
jest.mock("@sqldesk/viz/lib/services/offscreen", () => ({ revealAllCharts: jest.fn() }));
jest.mock("@/services/auth", () => ({ currentUser: { name: "Test" } }));
jest.mock("@/assets/images/sqldesk_icon.svg", () => "logo.svg", { virtual: true });
jest.mock("@/lib/utils", () => ({
  capitalizeFirst: (text) => text,
  formatDateTime: () => "1 Nov 2026",
}));
jest.mock("./compose", () => ({
  __esModule: true,
  // Async in the real module, and the capture races it against a timeout --
  // a plain object here fails on `.finally` rather than on anything real.
  default: jest.fn(() =>
    Promise.resolve({ width: 100, height: 100, toBlob: (done) => done(new Blob(["png"])) })
  ),
  PAGE_FURNITURE: { width: 80, height: 144, top: 104 },
}));

const { toSvg } = require("html-to-image");

/*
  The export drew nothing on a notebook, and said nothing about it.

  `captureGrid` draws tiles rather than the whole container, so that a widget
  which will not render is a labelled gap instead of a blank file. It has to
  be told what a tile is -- and a notebook asked with the dashboard's
  selector matched no elements at all, so the canvas was only its own
  background. There was no error anywhere: an empty list of tiles is exactly
  what an empty dashboard looks like, which is why both the PDF and the image
  came out blank rather than failing.
*/
function pageOf(className, count) {
  const container = document.createElement("div");
  Object.defineProperty(container, "scrollWidth", { value: 1200 });
  Object.defineProperty(container, "scrollHeight", { value: 2000 });
  container.getBoundingClientRect = () => ({ top: 0, left: 0, width: 1200, height: 2000 });
  for (let i = 0; i < count; i += 1) {
    const tile = document.createElement("div");
    tile.className = className;
    tile.getBoundingClientRect = () => ({ top: i * 300, left: 0, width: 1200, height: 280 });
    container.appendChild(tile);
  }
  return container;
}

// jsdom has no canvas implementation, and the capture only ever paints into
// one. A stub is enough: what this suite asks is which elements were handed
// to the renderer, not what the pixels came out as.
beforeAll(() => {
  HTMLCanvasElement.prototype.getContext = () => ({
    fillStyle: "",
    fillRect: () => {},
    drawImage: () => {},
    strokeRect: () => {},
    fillText: () => {},
    measureText: () => ({ width: 0 }),
    save: () => {},
    restore: () => {},
    setLineDash: () => {},
    beginPath: () => {},
    moveTo: () => {},
    lineTo: () => {},
    stroke: () => {},
  });
  HTMLCanvasElement.prototype.toBlob = (done) => done(new Blob(["png"]));
  HTMLCanvasElement.prototype.toDataURL = () => "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBD";
  // jsdom never loads an image, so the capture's own loader would wait out
  // its five-second timeout for every tile and report each as a gap.
  window.Image = class {
    set src(value) {
      this.value = value;
      setTimeout(() => this.onload && this.onload(), 0);
    }
  };
});

describe("what the capture treats as a tile", () => {
  beforeEach(() => jest.clearAllMocks());

  it("draws a notebook's cells when told they are the tiles", async () => {
    const notebook = pageOf("notebook-cell", 3);

    await renderDashboardToPng(notebook, { title: "Quarter", tiles: NOTEBOOK_TILES });

    // Three cells, three drawings. Before this was an argument it was zero,
    // and the export was a blank page with nothing reported.
    expect(toSvg).toHaveBeenCalledTimes(3);
  });

  it("still draws a dashboard's widgets, which is the default", async () => {
    const dashboard = pageOf("react-grid-item", 2);

    await renderDashboardToPng(dashboard, { title: "Sales" });

    expect(toSvg).toHaveBeenCalledTimes(2);
  });

  it("draws nothing from a notebook asked with the dashboard's selector", async () => {
    const notebook = pageOf("notebook-cell", 3);

    await renderDashboardToPng(notebook, { title: "Quarter", tiles: DASHBOARD_TILES });

    // The bug itself, pinned: this is what the notebook export used to do.
    expect(toSvg).not.toHaveBeenCalled();
  });
});
