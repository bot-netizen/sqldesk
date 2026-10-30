import React from "react";
import { shallow } from "enzyme";
import NotebookCell, { CellOutput } from "./NotebookCell";

jest.mock("@/services/notebook", () => ({
  saveCell: jest.fn(() => Promise.resolve({})),
  runCell: jest.fn(() => Promise.resolve({ job: { id: "j1" } })),
  stop: jest.fn(() => Promise.resolve({ stopped: true })),
  deleteCell: jest.fn(() => Promise.resolve({})),
  cellResult: jest.fn(() => Promise.resolve(null)),
}));
jest.mock("@/services/query-result", () => ({ fetchDataFromJob: jest.fn(() => Promise.resolve(1)) }));
jest.mock("@/services/notification", () => ({ warning: jest.fn(), success: jest.fn() }));
jest.mock("@/components/queries/editor-components", () => ({
  getEditorComponents: () => ({ QueryEditor: () => null }),
}));

const Notebook = require("@/services/notebook");

/*
  What a cell shows before it is run.

  The sentences here are the product rather than the chrome: Zeppelin's
  failure mode is discovering the limits by hitting them, so a cell that
  cannot run says why, a cell whose inputs moved on says that, and a cell whose
  input was deleted says something different again -- because those three need
  three different things done about them.
*/
function aCell(extras = {}) {
  return {
    id: 1,
    notebook_id: 5,
    name: "orders",
    kind: "sql",
    source: "SELECT 1",
    position: 0,
    data_source_id: 3,
    latest_result_id: null,
    last_run_at: null,
    options: {},
    cannot_run: null,
    reads: [],
    ...extras,
  };
}

function mount(cell, props = {}) {
  return shallow(
    <NotebookCell
      cell={cell}
      notebookId={5}
      dataSources={[{ id: 3, name: "Warehouse" }]}
      canEdit
      onChanged={jest.fn()}
      onRemoved={jest.fn()}
      onRunningChanged={jest.fn()}
      {...props}
    />
  );
}

describe("a cell that cannot run", () => {
  beforeEach(() => jest.clearAllMocks());

  it("says why, in the server's own words", () => {
    const page = mount(aCell({ cannot_run: "This cell has no SQL in it yet." }));

    expect(page.find('[data-test="CannotRun"]').prop("message")).toBe("This cell has no SQL in it yet.");
  });

  it("has Run disabled, so the reason is not something you find out by pressing it", () => {
    const page = mount(aCell({ cannot_run: "orders has not run yet." }));

    expect(page.find('[data-test="RunCell"]').prop("disabled")).toBe(true);
  });

  it("and a runnable cell has Run enabled", () => {
    const page = mount(aCell());

    expect(page.find('[data-test="RunCell"]').prop("disabled")).toBe(false);
  });

  it("cannot be run while another cell is running", () => {
    const page = mount(aCell(), { running: 9 });

    expect(page.find('[data-test="RunCell"]').prop("disabled")).toBe(true);
  });
});

describe("what a cell says about its own output", () => {
  it("marks itself stale, and does not pretend the number is current", () => {
    const page = mount(aCell({ last_run_at: "2026-10-30T09:00:00Z", stale_because_of: ["orders"] }));

    const notice = page.find('[data-test="Stale"]');
    expect(notice.exists()).toBe(true);
    expect(notice.prop("message")).toContain("older data");
    expect(notice.prop("type")).toBe("warning");
  });

  it("says a deleted input differently, because it cannot be re-run at all", () => {
    const page = mount(aCell({ last_run_at: "2026-10-30T09:00:00Z", missing_inputs: ["orders"] }));

    const notice = page.find('[data-test="MissingInputs"]');
    expect(notice.prop("message")).toContain("no longer exists");
    expect(notice.prop("type")).toBe("error");
  });

  it("names the cells it reads", () => {
    const page = mount(aCell({ reads: ["orders", "weather"] }));

    expect(page.find('[data-test="CellReads"]').text()).toContain("orders, weather");
  });
});

describe("running one", () => {
  beforeEach(() => jest.clearAllMocks());

  it("saves what is on the screen before running it", () => {
    const page = mount(aCell());
    page.find('[className="notebook-cell-editor"]').simulate("change", "SELECT 2");

    page.find('[data-test="RunCell"]').simulate("click");

    // Otherwise the cell runs its previous text, which is the single most
    // confusing thing a notebook can do.
    expect(Notebook.saveCell).toHaveBeenCalledWith(5, 1, { source: "SELECT 2" });
  });

  it("does not save when nothing was typed", async () => {
    const page = mount(aCell());

    page.find('[data-test="RunCell"]').simulate("click");
    // The run is a promise chain, so it reaches `runCell` on the next tick.
    await Promise.resolve();

    expect(Notebook.saveCell).not.toHaveBeenCalled();
    expect(Notebook.runCell).toHaveBeenCalledWith(5, 1);
  });

  it("offers Stop while it is running, not Run", () => {
    const page = mount(aCell(), { running: 1 });

    expect(page.find('[data-test="StopCell"]').exists()).toBe(true);
    expect(page.find('[data-test="RunCell"]').exists()).toBe(false);
  });
});

describe("a python cell", () => {
  it("is edited as python and offers no data source", () => {
    const page = mount(aCell({ kind: "python", source: "orders.head()", data_source_id: null }));

    expect(page.find('[className="notebook-cell-editor"]').prop("syntax")).toBe("python");
    expect(page.find('[data-test="CellDataSource"]').exists()).toBe(false);
  });
});

describe("the output", () => {
  it("draws a table when the cell produced one", () => {
    const output = shallow(
      <CellOutput
        cell={aCell({ last_run_at: "x" })}
        produced="table"
        result={{ data: { columns: [{ name: "id" }, { name: "city" }], rows: [{ id: 1, city: "Toronto" }] } }}
      />
    );

    const table = output.find("Table");
    // The columns and the row, not merely that a Table exists: an empty table
    // satisfies that, which is how this test first passed while the component
    // was reading the wrong level of the response.
    expect(table.prop("columns").map((column) => column.title)).toEqual(["id", "city"]);
    expect(table.prop("dataSource")).toEqual([{ id: 1, city: "Toronto", key: 0 }]);
  });

  it("says what the slice is a slice of, when there is more", () => {
    const output = shallow(
      <CellOutput
        cell={aCell({ last_run_at: "x" })}
        produced="table"
        result={{ data: { columns: [{ name: "id" }], rows: [{ id: 1 }] }, handed_on: 4200000 }}
      />
    );

    expect(output.find('[data-test="CellRowCount"]').text()).toContain("4,200,000");
  });

  it("and says nothing when the slice is the whole result", () => {
    const output = shallow(
      <CellOutput
        cell={aCell({ last_run_at: "x" })}
        produced="table"
        result={{ data: { columns: [{ name: "id" }], rows: [{ id: 1 }] }, handed_on: 1 }}
      />
    );

    expect(output.find('[data-test="CellRowCount"]').exists()).toBe(false);
  });

  it("draws the printout when it produced text, since nothing can read it", () => {
    const output = shallow(
      <CellOutput
        cell={aCell({ last_run_at: "x" })}
        produced="text"
        result={{ data: { columns: [{ name: "output" }], rows: [{ output: "looked at it" }] } }}
      />
    );

    expect(output.find("Table").exists()).toBe(false);
    expect(output.text()).toContain("looked at it");
  });

  it("says a cell produced text even before its output has loaded", () => {
    const output = shallow(<CellOutput cell={aCell({ last_run_at: "x" })} produced="text" result={null} />);

    expect(output.text()).toContain("produced text");
  });
});
