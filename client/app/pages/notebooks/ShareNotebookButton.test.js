import React from "react";
import { mount } from "enzyme";
import { act } from "react-dom/test-utils";
import ShareNotebookButton, { cellBreaks } from "./ShareNotebookButton";

jest.mock("@/services/notebook", () => ({
  share: jest.fn(() => Promise.resolve({})),
  unshare: jest.fn(() => Promise.resolve({})),
}));
jest.mock("@/services/notification", () => ({ success: jest.fn(), warning: jest.fn(), error: jest.fn() }));
jest.mock("../dashboards/export", () => ({
  exportSizeProblem: jest.fn(() => null),
  renderDashboardToPng: jest.fn(() => Promise.resolve({ blob: new Blob(["png"]) })),
  renderPagedPdf: jest.fn(() => Promise.resolve({ blob: new Blob(["pdf"]), pages: 4 })),
  downloadBlob: jest.fn(),
  filenameFor: (name, extension) => `${name}.${extension}`,
}));

const exportModule = require("../dashboards/export");

/*
  A notebook is a document, so its PDF is a document.

  The dashboard's PDF is a one-page report and refuses anything past a page.
  That rule is right for a dashboard and wrong here: a notebook is a study
  somebody wants to print, and the whole of it has to come out.
*/
function aNotebook(extras = {}) {
  return { id: 5, name: "Quarter", can_edit: true, is_draft: false, public_url: null, ...extras };
}

function mountButton(notebook = aNotebook(), target = document.createElement("div")) {
  return mount(<ShareNotebookButton notebook={notebook} getExportTarget={() => target} onChanged={jest.fn()} />);
}

async function choose(page, test) {
  // antd renders the menu into an overlay, so it has to be opened first.
  page.find('[data-test="ShareNotebook"]').first().simulate("click");
  page.update();
  await act(async () => {
    page.find(`[data-test="${test}"]`).first().simulate("click");
  });
}

describe("exporting a notebook", () => {
  beforeEach(() => jest.clearAllMocks());

  it("has no size limit on the PDF, because a PDF has pages", async () => {
    exportModule.exportSizeProblem.mockReturnValue("This dashboard has 40 widgets.");

    await choose(mountButton(), "SharePdf");

    // Asked at all, the dashboard's one-page rule would refuse this.
    expect(exportModule.exportSizeProblem).not.toHaveBeenCalled();
    expect(exportModule.renderPagedPdf).toHaveBeenCalled();
  });

  it("keeps the limit on the image, which is the browser's and not ours", async () => {
    exportModule.exportSizeProblem.mockReturnValue("larger than any image the browser will make");

    await choose(mountButton(), "ShareImage");

    expect(exportModule.renderDashboardToPng).not.toHaveBeenCalled();
  });

  it("tells the exporter where a page may end", async () => {
    const target = document.createElement("div");
    await choose(mountButton(aNotebook(), target), "SharePdf");

    expect(exportModule.renderPagedPdf.mock.calls[0][1]).toHaveProperty("breaks");
  });
});

describe("where a page may end", () => {
  it("is the bottom of each cell, measured from the top of the capture", () => {
    const target = document.createElement("div");
    target.getBoundingClientRect = () => ({ top: 100 });
    const cells = [420, 900, 1310].map((bottom) => {
      const cell = document.createElement("div");
      cell.className = "notebook-cell";
      cell.getBoundingClientRect = () => ({ bottom });
      return cell;
    });
    target.querySelectorAll = () => cells;

    // Relative to the capture, not the viewport: the page is scrolled and the
    // exporter knows nothing about where the window happens to be.
    expect(cellBreaks(target)).toEqual([320, 800, 1210]);
  });

  it("is empty for a notebook with no cells, which still exports", () => {
    const target = document.createElement("div");

    expect(cellBreaks(target)).toEqual([]);
  });
});
