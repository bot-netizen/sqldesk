import React from "react";
import { shallow, mount } from "enzyme";
import { act } from "react-dom/test-utils";
import NotebookPage, { InterpreterState, NotebookContents, NotebookSize, countOf } from "./Notebook";

// A factory inside the mock would be an out-of-scope reference, which jest
// refuses: each test supplies what `get` should answer with.
jest.mock("@/services/notebook", () => ({
  get: jest.fn(() => Promise.resolve({})),
  addCell: jest.fn(() => Promise.resolve({})),
  detach: jest.fn(() => Promise.resolve({ detached: true })),
  save: jest.fn(() => Promise.resolve({})),
}));
jest.mock("@/services/data-source", () => ({ query: jest.fn(() => Promise.resolve([])) }));
jest.mock("@/services/notification", () => ({ success: jest.fn(), warning: jest.fn() }));
jest.mock("./NotebookCell", () => () => null);

const Notebook = require("@/services/notebook");

function fixture(extras = {}) {
  return {
    id: 5,
    name: "Quarter",
    is_draft: false,
    can_edit: true,
    interpreter: { configured: true, attached: false },
    cells: [{ id: 1, name: "orders", kind: "sql", position: 0, source: "SELECT 1", options: {} }],
    ...extras,
  };
}

/*
  Mounted, not shallow. Enzyme's shallow renderer does not run `useEffect`, so
  a page that loads what it shows in one would never load anything at all --
  which is what four of these tests reported before this was mount.
*/
async function open(notebook = fixture()) {
  Notebook.get.mockResolvedValueOnce(notebook);
  let page;
  await act(async () => {
    page = mount(<NotebookPage notebookId={5} />);
  });
  page.update();
  return page;
}

describe("opening a notebook", () => {
  beforeEach(() => jest.clearAllMocks());

  it("fetches it once and draws its cells", async () => {
    const page = await open();

    expect(Notebook.get).toHaveBeenCalledWith(5);
    expect(page.find('[data-test="NotebookName"]').text()).toBe("Quarter");
  });

  it("says a notebook with no cells starts with SQL, because a code cell cannot query", async () => {
    const page = await open(fixture({ cells: [] }));

    expect(page.find("Alert.notebook-empty").prop("description")).toContain("cannot query");
  });

  it("offers Publish only while it is a draft", async () => {
    expect((await open(fixture({ is_draft: true }))).find('[data-test="PublishNotebook"]').exists()).toBe(true);
    expect((await open(fixture({ is_draft: false }))).find('[data-test="PublishNotebook"]').exists()).toBe(false);
  });

  it("offers no editing at all to somebody who may only read it", async () => {
    const page = await open(fixture({ can_edit: false }));

    expect(page.find('[data-test="AddCell"]').exists()).toBe(false);
  });

  it("shows the message rather than the page when it cannot be opened", async () => {
    Notebook.get.mockRejectedValueOnce(new Error("nope"));
    let page;
    await act(async () => {
      page = mount(<NotebookPage notebookId={5} />);
    });
    page.update();

    expect(page.find(".notebook-load-error").exists()).toBe(true);
    expect(page.find('[data-test="NotebookPage"]').exists()).toBe(false);
  });
});

/*
  The three interpreter states, which lead to three different actions: ask an
  administrator, wait for the first run to attach, or let a live one go.
*/
describe("what the header says about the interpreter", () => {
  it("names the absence when none is configured", () => {
    const state = shallow(<InterpreterState state={{ configured: false, attached: false }} onDetach={jest.fn()} />);

    expect(state.find('[data-test="InterpreterState"]').text()).toBe("No interpreter");
  });

  it("says ready, not attached, when one is configured and idle", () => {
    const state = shallow(<InterpreterState state={{ configured: true, attached: false }} onDetach={jest.fn()} />);

    expect(state.find('[data-test="InterpreterState"]').text()).toBe("Interpreter ready");
  });

  it("offers to let an attached one go", () => {
    const onDetach = jest.fn();
    const state = shallow(<InterpreterState state={{ configured: true, attached: true }} onDetach={onDetach} />);

    state.find('[data-test="DetachInterpreter"]').simulate("click");

    expect(onDetach).toHaveBeenCalled();
  });
});

/*
  The contents, and the size.

  The contents list is the single biggest reason a Zeppelin notebook of thirty
  cells is navigable and ours was not -- and the reason a cell can be titled
  at all, because a list reading `cell_1 … cell_30` is one nobody reads.
*/
describe("the contents", () => {
  const cells = [
    { id: 1, name: "cell_1", title: "Orders", kind: "sql" },
    { id: 2, name: "code_1", title: null, kind: "python" },
    { id: 3, name: "cell_2", title: "Takings", kind: "sql" },
  ];

  it("lists a title where there is one and the name where there is not", () => {
    const contents = shallow(<NotebookContents cells={cells} />);
    const entries = contents.find("a").map((one) => one.text());

    expect(entries).toEqual(["Orders", "code_1", "Takings"]);
  });

  it("points each entry at its cell", () => {
    const contents = shallow(<NotebookContents cells={cells} />);

    expect(contents.find('[data-test="ContentsEntry-cell_1"]').prop("href")).toBe("#cell-1");
  });

  it("marks a folded cell as put away rather than dropping it", () => {
    const folded = [...cells.slice(0, 2), { ...cells[2], options: { collapsed: true } }];
    const contents = shallow(<NotebookContents cells={folded} />);

    expect(contents.find('[data-test="ContentsEntry-cell_2"]').hasClass("notebook-contents-folded")).toBe(true);
  });

  it("is not drawn for a notebook too small to need it", () => {
    // A contents list for two cells is furniture.
    expect(shallow(<NotebookContents cells={cells.slice(0, 2)} />).isEmptyRender()).toBe(true);
  });
});

describe("how big a notebook is", () => {
  it("counts a warehouse once however many cells hit it", () => {
    // Eight cells against one warehouse is one source; saying "8 data sources"
    // would make a notebook look like it reaches further than it does.
    const counted = countOf([
      { id: 1, data_source_id: 4 },
      { id: 2, data_source_id: 4 },
      { id: 3, data_source_id: 9 },
    ]);

    expect(counted).toEqual({ cells: 3, dataSources: 2 });
  });

  it("does not count a cell that reads earlier cells as a data source", () => {
    const counted = countOf([{ id: 1, data_source_id: 4 }, { id: 2, data_source_id: null }]);

    expect(counted.dataSources).toBe(1);
  });

  it("says it in words, singular where it should be", () => {
    const size = shallow(<NotebookSize cells={[{ id: 1, data_source_id: 4 }]} />);

    expect(size.text()).toContain("1 cell");
    expect(size.text()).toContain("1 data source");
  });

  it("says so when nothing touches a warehouse", () => {
    const size = shallow(<NotebookSize cells={[{ id: 1, data_source_id: null }]} />);

    expect(size.text()).toContain("no data source");
  });

  it("shows nothing for an empty notebook", () => {
    expect(shallow(<NotebookSize cells={[]} />).isEmptyRender()).toBe(true);
  });
});
