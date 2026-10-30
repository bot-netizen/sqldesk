import React from "react";
import { shallow, mount } from "enzyme";
import { act } from "react-dom/test-utils";
import NotebookPage, { InterpreterState } from "./Notebook";

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
