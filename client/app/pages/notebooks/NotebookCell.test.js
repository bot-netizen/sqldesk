import React from "react";
import { shallow, mount as mountFully } from "enzyme";
import { act } from "react-dom/test-utils";
import NotebookCell, { CellOutput, CellTitle, summarise } from "./NotebookCell";

jest.mock("@/services/notebook", () => ({
  saveCell: jest.fn(() => Promise.resolve({})),
  runCell: jest.fn(() => Promise.resolve({ job: { id: "j1" } })),
  stop: jest.fn(() => Promise.resolve({ stopped: true })),
  deleteCell: jest.fn(() => Promise.resolve({})),
  cellResult: jest.fn(() => Promise.resolve(null)),
  downloadUrl: (notebookId, cellId) => `api/notebooks/${notebookId}/cells/${cellId}/download`,
}));
jest.mock("@/services/query-result", () => ({ fetchDataFromJob: jest.fn(() => Promise.resolve(1)) }));
jest.mock("@/services/notification", () => ({ warning: jest.fn(), success: jest.fn() }));
jest.mock("@/components/queries/editor-components", () => ({
  getEditorComponents: () => ({ QueryEditor: () => null }),
}));
jest.mock("@/components/visualizations/visualizationComponents", () => ({ Renderer: () => null }));
jest.mock("./CellVisualizationDialog", () => ({ showModal: jest.fn(() => ({ onClose: () => {} })) }));

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

  it("stops saying a cell is empty the moment something is typed into it", () => {
    // The refusal describes the cell as saved, and a cell saves on blur. Left
    // alone, this told somebody who had just typed SQL that the cell had none,
    // with Run disabled, until they clicked somewhere else.
    const page = mount(aCell({ source: "", cannot_run: "This cell has no SQL in it yet.", cannot_run_code: "empty" }));

    expect(page.find('[data-test="RunCell"]').prop("disabled")).toBe(true);
    page.find('[className="notebook-cell-editor"]').simulate("change", "SELECT 1");

    expect(page.find('[data-test="RunCell"]').prop("disabled")).toBe(false);
    expect(page.find('[data-test="CannotRun"]').exists()).toBe(false);
  });

  it("keeps every other refusal while somebody types, because typing does not fix them", () => {
    const page = mount(aCell({ source: "", cannot_run: "orders has not run yet.", cannot_run_code: "unrun_input" }));

    page.find('[className="notebook-cell-editor"]').simulate("change", "SELECT count(*) FROM orders");

    expect(page.find('[data-test="RunCell"]').prop("disabled")).toBe(true);
    expect(page.find('[data-test="CannotRun"]').exists()).toBe(true);
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

describe("the chart button", () => {
  /*
    Mounted, because the rows arrive in an effect and a shallow render does
    not run effects -- so every one of these would pass without the button
    ever being considered.
  */
  async function withOutput(cell, rows) {
    Notebook.cellResult.mockResolvedValueOnce({
      data: { columns: [{ name: "id" }], rows },
      handed_on: rows.length,
    });
    let page;
    await act(async () => {
      page = mountFully(
        <NotebookCell
          cell={cell}
          notebookId={5}
          dataSources={[]}
          canEdit
          onChanged={jest.fn()}
          onRemoved={jest.fn()}
          onRunningChanged={jest.fn()}
        />
      );
    });
    page.update();
    return page;
  }

  beforeEach(() => jest.clearAllMocks());

  it("is offered once a cell has produced a table and its rows are loaded", async () => {
    const page = await withOutput(aCell({ last_run_at: "x", latest_result_id: 7, options: { produced: "table" } }), [
      { id: 1 },
    ]);

    expect(page.find('[data-test="VisualizeCell"]').exists()).toBe(true);
  });

  it("is not offered for a cell that produced text, which nothing can chart", async () => {
    const page = await withOutput(aCell({ last_run_at: "x", latest_result_id: 7, options: { produced: "text" } }), [
      { id: 1 },
    ]);

    expect(page.find('[data-test="VisualizeCell"]').exists()).toBe(false);
  });

  it("is not offered before the rows have arrived", async () => {
    Notebook.cellResult.mockResolvedValueOnce(null);
    let page;
    await act(async () => {
      page = mountFully(
        <NotebookCell
          cell={aCell({ last_run_at: "x", latest_result_id: 7, options: { produced: "table" } })}
          notebookId={5}
          dataSources={[]}
          canEdit
          onChanged={jest.fn()}
          onRemoved={jest.fn()}
          onRunningChanged={jest.fn()}
        />
      );
    });
    page.update();

    expect(page.find('[data-test="VisualizeCell"]').exists()).toBe(false);
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

  it("draws the chart instead of the table once a cell has one", () => {
    const output = shallow(
      <CellOutput
        cell={aCell({ last_run_at: "x", options: { visualization: { type: "CHART", name: "By city", options: {} } } })}
        produced="table"
        result={{ data: { columns: [{ name: "id" }], rows: [{ id: 1 }] } }}
        onRemoveChart={jest.fn()}
      />
    );

    expect(output.find("Table").exists()).toBe(false);
    expect(output.find("Renderer").exists()).toBe(true);
    // And a way back, because a chart of the wrong column is the usual
    // outcome of the first attempt.
    expect(output.find('[data-test="RemoveChart"]').exists()).toBe(true);
  });

  it("offers no way back when nothing can take one", () => {
    const output = shallow(
      <CellOutput
        cell={aCell({ last_run_at: "x", options: { visualization: { type: "CHART", name: "By city", options: {} } } })}
        produced="table"
        result={{ data: { columns: [{ name: "id" }], rows: [{ id: 1 }] } }}
        onRemoveChart={null}
      />
    );

    expect(output.find('[data-test="RemoveChart"]').exists()).toBe(false);
    expect(output.find("Renderer").exists()).toBe(true, "the chart went with the button");
  });

  it("says a cell produced text even before its output has loaded", () => {
    const output = shallow(<CellOutput cell={aCell({ last_run_at: "x" })} produced="text" result={null} />);

    expect(output.text()).toContain("produced text");
  });
});

/*
  What the cell printed, shown with whatever it produced.

  A cell that prints its diagnostics and then shows a dataframe lost the
  printing entirely -- the server only carried it when it arrived *instead of*
  a table. These assert the page shows both, and does not show the same lines
  twice when the printing is the output.
*/
describe("what the cell printed", () => {
  const table = { columns: [{ name: "id" }], rows: [{ id: 1 }] };

  it("shows it above the table", () => {
    const output = shallow(
      <CellOutput cell={aCell({ last_run_at: "x" })} produced="table" result={{ data: table, printed: "rows: 42" }} />
    );

    expect(output.find('[data-test="CellPrinted"]').text()).toBe("rows: 42");
    expect(output.find("Table").exists()).toBe(true);
  });

  it("shows nothing at all when the cell printed nothing", () => {
    const output = shallow(
      <CellOutput cell={aCell({ last_run_at: "x" })} produced="table" result={{ data: table, printed: null }} />
    );

    expect(output.find('[data-test="CellPrinted"]').exists()).toBe(false);
  });

  it("does not repeat it when the printing is itself the output", () => {
    // `produced === "text"` puts the printing in the single `output` column,
    // so showing `printed` too would draw the same lines twice.
    const output = shallow(
      <CellOutput
        cell={aCell({ last_run_at: "x" })}
        produced="text"
        result={{ data: { columns: [{ name: "output" }], rows: [{ output: "looked at it" }] }, printed: "looked at it" }}
      />
    );

    expect(output.find('[data-test="CellPrinted"]').exists()).toBe(false);
    expect(output.find('[data-test="CellOutput"]').text()).toContain("looked at it");
  });

  it("shows it above a chart too, where the table is replaced", () => {
    const output = shallow(
      <CellOutput
        cell={aCell({ last_run_at: "x", options: { visualization: { name: "Chart", type: "CHART", options: {} } } })}
        produced="table"
        result={{ data: table, printed: "fitted in 0.4s" }}
      />
    );

    expect(output.find('[data-test="CellPrinted"]').text()).toBe("fitted in 0.4s");
    expect(output.find("Renderer").exists()).toBe(true);
  });
});

/*
  The document layer: a title, folding, and the two visibility toggles.

  All three persist on the cell rather than in the browser, which Zeppelin
  also does and for the same reason: somebody who folds a notebook into a
  readable report has done work, and that work is for whoever opens it next.
*/
describe("the title a person gives a step", () => {
  it("falls back to the cell's name when there is none", () => {
    const title = shallow(<CellTitle cell={aCell({ title: null })} canEdit onChange={jest.fn()} />);

    expect(title.find('[data-test="CellTitle"]').text()).toBe("Name this step");
  });

  it("shows the title once there is one", () => {
    const title = shallow(<CellTitle cell={aCell({ title: "Orders, cleaned" })} canEdit onChange={jest.fn()} />);

    expect(title.find('[data-test="CellTitle"]').text()).toBe("Orders, cleaned");
  });

  it("saves what was typed, trimmed", () => {
    const onChange = jest.fn();
    const title = shallow(<CellTitle cell={aCell({ title: null })} canEdit onChange={onChange} />);
    title.find('[data-test="CellTitle"]').simulate("click");
    title.find('[data-test="CellTitleInput"]').simulate("change", { target: { value: "  Orders  " } });
    title.find('[data-test="CellTitleInput"]').simulate("blur");

    expect(onChange).toHaveBeenCalledWith("Orders");
  });

  it("abandons the edit on Escape, keeping what was there", () => {
    const onChange = jest.fn();
    const title = shallow(<CellTitle cell={aCell({ title: "Orders" })} canEdit onChange={onChange} />);
    title.find('[data-test="CellTitle"]').simulate("click");
    title.find('[data-test="CellTitleInput"]').simulate("change", { target: { value: "Something else" } });
    title.find('[data-test="CellTitleInput"]').simulate("keydown", { key: "Escape" });

    expect(onChange).not.toHaveBeenCalled();
    expect(title.find('[data-test="CellTitle"]').text()).toBe("Orders");
  });

  it("offers no editing at all to somebody who may not edit", () => {
    const title = shallow(<CellTitle cell={aCell({ title: "Orders" })} canEdit={false} onChange={jest.fn()} />);
    title.find('[data-test="CellTitle"]').simulate("click");

    expect(title.find('[data-test="CellTitleInput"]').exists()).toBe(false);
  });

  it("shows nothing rather than a prompt to a reader who cannot set one", () => {
    const title = shallow(<CellTitle cell={aCell({ title: null })} canEdit={false} onChange={jest.fn()} />);

    expect(title.isEmptyRender()).toBe(true);
  });
});

describe("what a folded cell says for itself", () => {
  it("admits it has not run", () => {
    expect(summarise(aCell({ last_run_at: null }), undefined)).toBe("Not run yet.");
  });

  it("says a table, so folding hides the work and not the fact of it", () => {
    expect(summarise(aCell({ last_run_at: "x" }), "table")).toBe("Produced a table.");
  });

  it("says text", () => {
    expect(summarise(aCell({ last_run_at: "x" }), "text")).toBe("Produced text.");
  });
});

/*
  Taking a result out of here.

  The link points at the endpoint that reads the notebook's own store, which
  holds the whole handoff -- not at the truncated slice `query_results` keeps
  for the page. An anchor rather than a click handler, so the browser's own
  download handles Content-Disposition.
*/
describe("downloading a cell's output", () => {
  const table = { columns: [{ name: "id" }], rows: [{ id: 1 }] };

  function cellWith(extras) {
    return mountFully(
      <NotebookCell
        cell={aCell(extras)}
        notebookId={7}
        canEdit
        onChanged={jest.fn()}
        onRemoved={jest.fn()}
        onRunningChanged={jest.fn()}
      />
    );
  }

  it("is offered on a cell that produced a table", () => {
    const cell = cellWith({ last_run_at: "x", options: { produced: "table" } });

    const link = cell.find('[data-test="DownloadCell"]').first();
    expect(link.exists()).toBe(true);
    expect(link.prop("href")).toBe("api/notebooks/7/cells/1/download");
  });

  it("is not offered on a cell that printed, which has no relation to take", () => {
    const cell = cellWith({ last_run_at: "x", options: { produced: "text" } });

    expect(cell.find('[data-test="DownloadCell"]').exists()).toBe(false);
  });

  it("is not offered before the cell has run", () => {
    const cell = cellWith({ last_run_at: null, options: { produced: "table" } });

    expect(cell.find('[data-test="DownloadCell"]').exists()).toBe(false);
  });

  it("is hidden with the rest of a folded cell", () => {
    const cell = cellWith({ last_run_at: "x", options: { produced: "table", collapsed: true } });

    expect(cell.find('[data-test="DownloadCell"]').exists()).toBe(false);
  });
});
