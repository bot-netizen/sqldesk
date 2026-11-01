import React from "react";
import { shallow, mount as mountFully } from "enzyme";
import { act } from "react-dom/test-utils";
import NotebookCell, {
  AvailableToRead,
  CellHandle,
  CellOutput,
  ResizableChart,
  RunsOn,
  describeWhatItRunsOn,
  summarise,
} from "./NotebookCell";
import EditableTitle from "./EditableTitle";

jest.mock("@/services/notebook", () => ({
  saveCell: jest.fn(() => Promise.resolve({})),
  runCell: jest.fn(() => Promise.resolve({ job: { id: "j1" } })),
  stop: jest.fn(() => Promise.resolve({ stopped: true })),
  deleteCell: jest.fn(() => Promise.resolve({})),
  cellResult: jest.fn(() => Promise.resolve(null)),
  downloadUrl: (notebookId, cellId) => `api/notebooks/${notebookId}/cells/${cellId}/download`,
}));
jest.mock("@/services/query-result", () => ({ fetchDataFromJob: jest.fn(() => Promise.resolve(1)) }));
jest.mock("@/services/notification", () => ({ warning: jest.fn(), success: jest.fn(), error: jest.fn() }));
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

  it("does not say what the cell reads, which is the cell's own business", () => {
    // The header carried "reads orders, weather" beside the handle. A cell
    // may read any of the cells above it or none, and listing them described
    // somebody's code back to them on every row of a long notebook. What is
    // *available* is still said under the editor, where it is useful.
    const page = mount(aCell({ reads: ["orders", "weather"] }));

    expect(page.find('[data-test="CellReads"]').exists()).toBe(false);
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
    // From the output's own tab bar, where somebody looking at a table is
    // already looking. The cell menu carries it too, which the menu test
    // below covers.
    const page = await withOutput(aCell({ last_run_at: "x", latest_result_id: 7, options: { produced: "table" } }), [
      { id: 1 },
    ]);

    expect(page.find('[data-test="AddVisualization"]').exists()).toBe(true);
  });

  it("is not offered for a cell that produced text, which nothing can chart", async () => {
    const page = await withOutput(aCell({ last_run_at: "x", latest_result_id: 7, options: { produced: "text" } }), [
      { id: 1 },
    ]);

    expect(page.find('[data-test="AddVisualization"]').exists()).toBe(false);
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

  it("says how many rows and how long, when the slice is the whole result", () => {
    // Two questions people ask of a result before reading a row of it.
    const output = shallow(
      <CellOutput
        cell={aCell({ last_run_at: "x" })}
        produced="table"
        result={{ data: { columns: [{ name: "id" }], rows: [{ id: 1 }] }, handed_on: 1, runtime: 0.3 }}
      />
    );

    const said = output.find('[data-test="CellRowCount"]').text();
    expect(said).toContain("1 row");
    expect(said).toContain("0.30s");
  });

  it("still says what the slice is a slice of, when there is more", () => {
    const output = shallow(
      <CellOutput
        cell={aCell({ last_run_at: "x" })}
        produced="table"
        result={{ data: { columns: [{ name: "id" }], rows: [{ id: 1 }] }, handed_on: 4200000, runtime: 2.5 }}
      />
    );

    expect(output.find('[data-test="CellRowCount"]').text()).toContain("4,200,000");
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

  it("offers the chart beside the table rather than instead of it", () => {
    // It used to replace the table, with a link to get back, which made a
    // chart feel like a mode. One result, two tabs, and switching costs
    // nothing because both draw the rows already on the page.
    const output = shallow(
      <CellOutput
        cell={aCell({ last_run_at: "x", options: { visualization: { type: "CHART", name: "By city", options: {} } } })}
        produced="table"
        result={{ data: { columns: [{ name: "id" }], rows: [{ id: 1 }] } }}
        onRemoveChart={jest.fn()}
      />
    );

    const tabs = output.find("Tabs");
    expect(tabs.exists()).toBe(true);
    // The chart is what opens, because a cell that has one was given one on
    // purpose.
    expect(tabs.prop("defaultActiveKey")).toBe("chart");
    expect(output.find("Table").exists()).toBe(true);
    expect(output.find("Renderer").exists()).toBe(true);
    // And a way back, because a chart of the wrong column is the usual
    // outcome of the first attempt. Mounted from the TabPane's `tab` prop:
    // that is a prop holding an element, and shallow does not render into
    // props -- the same trap as an antd Dropdown's overlay.
    const chartTab = output.find("TabPane").filterWhere((one) => one.key() === "chart");
    expect(mountFully(<div>{chartTab.prop("tab")}</div>).find('[data-test="RemoveChart"]').exists()).toBe(true);
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
describe("a name you change by clicking it", () => {
  function title(props = {}) {
    return mountFully(<EditableTitle canEdit onChange={jest.fn()} placeholder="Name this step" {...props} />);
  }

  it("shows the placeholder when there is no name", () => {
    expect(title({ value: "" }).find('[data-test="EditableTitleInput"]').exists()).toBe(false);
    expect(title({ value: "" }).text()).toBe("Name this step");
  });

  it("shows the name once there is one", () => {
    expect(title({ value: "Orders, cleaned" }).text()).toBe("Orders, cleaned");
  });

  it("saves what was typed, trimmed", () => {
    const onChange = jest.fn();
    const made = title({ value: "", onChange });
    made.find('[data-test="EditableTitle"]').first().simulate("click");
    made.find("input").simulate("change", { target: { value: "  Orders  " } });
    made.find("input").simulate("blur");

    expect(onChange).toHaveBeenCalledWith("Orders");
  });

  it("abandons the edit on Escape, keeping what was there", () => {
    const onChange = jest.fn();
    const made = title({ value: "Orders", onChange });
    made.find('[data-test="EditableTitle"]').first().simulate("click");
    made.find("input").simulate("change", { target: { value: "Something else" } });
    made.find("input").simulate("keydown", { key: "Escape" });

    expect(onChange).not.toHaveBeenCalled();
    expect(made.text()).toBe("Orders");
  });

  it("saves nothing when the name did not actually change", () => {
    const onChange = jest.fn();
    const made = title({ value: "Orders", onChange });
    made.find('[data-test="EditableTitle"]').first().simulate("click");
    made.find("input").simulate("blur");

    expect(onChange).not.toHaveBeenCalled();
  });

  it("offers no editing at all to somebody who may not edit", () => {
    const made = title({ value: "Orders", canEdit: false });
    made.find('[data-test="EditableTitle"]').first().simulate("click");

    expect(made.find("input").exists()).toBe(false);
  });

  it("shows nothing rather than a prompt to a reader who cannot set one", () => {
    expect(title({ value: "", canEdit: false }).isEmptyRender()).toBe(true);
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

/*
  What a cell runs on.

  One control rather than two. The page used to fix the kind at Add-cell time
  and put a data source dropdown beside it, which left somebody looking at a
  Python cell wondering what the empty dropdown meant -- the answer being
  that it did not apply to them. The groups are the separation; the sentence
  beside the control is that separation readable while the dropdown is shut.
*/
describe("what a cell runs on", () => {
  const sources = [
    { id: 4, name: "Warehouse" },
    { id: 9, name: "Replica" },
  ];

  it("shows the warehouse a SQL cell queries", () => {
    const said = describeWhatItRunsOn({ kind: "sql", data_source_id: 4 }, sources, false);

    expect(said).toBe("SQL against Warehouse");
  });

  /*
    These words are a reader's only account of what a cell runs on, and they
    are worded as the control's own options are -- so an editor and a reader
    cannot end up describing the same cell differently.
  */
  it("names a SQL cell over earlier cells as the control does", () => {
    const said = describeWhatItRunsOn({ kind: "sql", data_source_id: null }, sources, false);

    expect(said).toBe("SQL over earlier cells");
  });

  it("names a Python cell as the control does", () => {
    const said = describeWhatItRunsOn({ kind: "python", data_source_id: null }, sources, false);

    expect(said).toBe("Python");
  });

  it("mentions the cluster when there is one to reach", () => {
    const said = describeWhatItRunsOn({ kind: "python" }, sources, true);

    expect(said).toContain("Spark");
  });

  it("does not invent a warehouse name the reader cannot see", () => {
    // A cell pointed at a data source this person has no access to: saying
    // nothing would read as "earlier cells", which is a different thing.
    const said = describeWhatItRunsOn({ kind: "sql", data_source_id: 77 }, sources, false);

    expect(said).toContain("cannot see");
  });

  it("selects the warehouse the cell is pointed at", () => {
    const control = shallow(
      <RunsOn cell={aCell({ kind: "sql", data_source_id: 9 })} dataSources={sources} canEdit onChange={jest.fn()} />
    );

    expect(control.find("Select").prop("value")).toBe("source:9");
  });

  it("switches a cell to Python and drops its data source in one change", () => {
    const onChange = jest.fn();
    const control = shallow(
      <RunsOn cell={aCell({ kind: "sql", data_source_id: 4 })} dataSources={sources} canEdit onChange={onChange} />
    );
    control.find("Select").simulate("change", "python");

    expect(onChange).toHaveBeenCalledWith({ kind: "python", data_source_id: null });
  });

  it("switches a Python cell back to a warehouse", () => {
    const onChange = jest.fn();
    const control = shallow(
      <RunsOn cell={aCell({ kind: "python" })} dataSources={sources} canEdit onChange={onChange} />
    );
    control.find("Select").simulate("change", "source:4");

    expect(onChange).toHaveBeenCalledWith({ kind: "sql", data_source_id: 4 });
  });

  it("offers a reader the words without the control", () => {
    const control = shallow(
      <RunsOn cell={aCell({ kind: "python" })} dataSources={sources} canEdit={false} onChange={jest.fn()} />
    );

    expect(control.find("Select").exists()).toBe(false);
    expect(control.text()).toContain("Python");
  });

  it("says nothing beside the control, which already says it", () => {
    // A sentence repeating the chosen value in longer words, on every cell of
    // every notebook: helpful once, noise thereafter.
    const control = shallow(
      <RunsOn cell={aCell({ kind: "python" })} dataSources={sources} canEdit onChange={jest.fn()} />
    );

    expect(control.find('[data-test="RunsOnSaid"]').exists()).toBe(false);
  });

  it("carries an option for a data source the reader cannot see", () => {
    // Without one the control falls back to showing the raw value, and the
    // header reads `source:9`.
    const control = shallow(
      <RunsOn cell={aCell({ data_source_id: 99 })} dataSources={sources} canEdit onChange={jest.fn()} />
    );

    // The Select carries the same value, so match on the option's own text.
    const unseen = control.findWhere(
      (node) => node.name() === "Option" && node.prop("value") === "source:99"
    );
    expect(unseen.exists()).toBe(true);
    expect(unseen.prop("disabled")).toBe(true);
  });

  it("hangs its menu on the page, so it travels with the cell", () => {
    // The window is not this app's scroller, so an overlay anchored to the
    // body stays where it opened while the page moves under it.
    const control = shallow(
      <RunsOn cell={aCell()} dataSources={sources} canEdit onChange={jest.fn()} />
    );

    const page = document.createElement("div");
    page.className = "notebook-page";
    const inside = document.createElement("span");
    page.appendChild(inside);

    expect(control.find("Select").prop("getPopupContainer")(inside)).toBe(page);
  });
});

/*
  How big a chart is drawn.

  Kept on the cell like the other view settings, so the person who sized a
  chart to be readable sized it for whoever opens the notebook next.
*/
describe("sizing a chart", () => {
  const withChart = (extras = {}) =>
    shallow(
      <CellOutput
        cell={aCell({
          last_run_at: "x",
          options: { visualization: { type: "CHART", name: "By city", options: {} }, ...extras },
        })}
        produced="table"
        result={{ data: { columns: [{ name: "id" }], rows: [{ id: 1 }] } }}
        onResizeChart={jest.fn()}
        onAddVisualization={jest.fn()}
      />
    );

  it("draws it at a readable height by default", () => {
    expect(withChart().find("ResizableChart").prop("height")).toBe(420);
  });

  it("uses the height the cell was dragged to", () => {
    expect(withChart({ chartHeight: 680 }).find("ResizableChart").prop("height")).toBe(680);
  });

  it("offers a handle to drag", () => {
    const chart = mountFully(
      <ResizableChart height={400} onResize={jest.fn()}>
        <div />
      </ResizableChart>
    );

    expect(chart.find('[data-test="ChartResizeHandle"]').exists()).toBe(true);
  });

  it("saves the height once, on release, not on every pixel", () => {
    // A save per mouse move would be a hundred requests for one drag.
    const onResize = jest.fn();
    const chart = mountFully(
      <ResizableChart height={400} onResize={onResize}>
        <div />
      </ResizableChart>
    );
    chart.find('[data-test="ChartResizeHandle"]').first().simulate("mousedown", { clientY: 100 });
    window.dispatchEvent(new MouseEvent("mousemove", { clientY: 150 }));
    window.dispatchEvent(new MouseEvent("mousemove", { clientY: 220 }));
    expect(onResize).not.toHaveBeenCalled();

    window.dispatchEvent(new MouseEvent("mouseup"));

    expect(onResize).toHaveBeenCalledTimes(1);
    expect(onResize).toHaveBeenCalledWith(520);
  });

  it("will not let a chart be dragged smaller than its own handle", () => {
    const onResize = jest.fn();
    const chart = mountFully(
      <ResizableChart height={200} onResize={onResize}>
        <div />
      </ResizableChart>
    );
    chart.find('[data-test="ChartResizeHandle"]').first().simulate("mousedown", { clientY: 500 });
    window.dispatchEvent(new MouseEvent("mousemove", { clientY: 0 }));
    window.dispatchEvent(new MouseEvent("mouseup"));

    expect(onResize).toHaveBeenCalledWith(160);
  });

  it("offers no handle to a reader who cannot change the notebook", () => {
    const chart = mountFully(
      <ResizableChart height={400}>
        <div />
      </ResizableChart>
    );

    expect(chart.find('[data-test="ChartResizeHandle"]').exists()).toBe(false);
  });
});

/*
  How somebody finds out how to read a particular cell.

  This is the one thing a notebook has that a query does not, and for a while
  the page had no visible handle for it at all: only the title was drawn, so
  the name a later cell has to type was nowhere a person was. These are the
  three places it is now -- on the cell, under the editor, and in what the
  editor completes against.
*/
describe("how to get at a cell's data", () => {
  beforeEach(() => jest.clearAllMocks());

  it("shows the name the cells below have to type", () => {
    const page = mount(aCell({ name: "orders", title: "Orders, cleaned" }));

    // Shallow, so the chip itself is one level down -- what matters here is
    // that the handle is drawn beside the title and carries the name.
    expect(page.find(CellHandle).prop("cell").name).toBe("orders");
  });

  it("shows it to a reader too, who is often about to write a cell", () => {
    const page = mount(aCell({ name: "orders" }), { canEdit: false });

    expect(page.find(CellHandle).exists()).toBe(true);
  });

  it("copies it, because the next thing anybody does is paste it below", async () => {
    const writeText = jest.fn(() => Promise.resolve());
    Object.defineProperty(window.navigator, "clipboard", { value: { writeText }, configurable: true });
    const handle = mountFully(<CellHandle cell={aCell({ name: "orders" })} canEdit />);

    handle.find('[data-test="CellHandle"]').first().simulate("click");

    expect(writeText).toHaveBeenCalledWith("orders");
  });

  it("renames it from the menu, where the server owns the rules", () => {
    const onRename = jest.fn(() => Promise.resolve({}));
    const handle = mountFully(
      <CellHandle cell={aCell({ name: "cell_1" })} canEdit editing onEditing={jest.fn()} onRename={onRename} />
    );

    const box = handle.find('[data-test="CellHandleInput"]');
    box.simulate("change", { target: { value: "orders" } });
    handle.find('[data-test="CellHandleInput"]').simulate("blur");

    expect(onRename).toHaveBeenCalledWith("orders");
  });

  it("abandons a rename on Escape rather than saving what was typed", () => {
    const onRename = jest.fn(() => Promise.resolve({}));
    const handle = mountFully(
      <CellHandle cell={aCell({ name: "cell_1" })} canEdit editing onEditing={jest.fn()} onRename={onRename} />
    );

    handle.find('[data-test="CellHandleInput"]').simulate("change", { target: { value: "orders" } });
    // Escape blurs, and blur is what saves -- so this is the ordering the
    // abandon flag exists for.
    handle.find('[data-test="CellHandleInput"]').simulate("keydown", { key: "Escape", target: { blur: () => {} } });
    handle.find('[data-test="CellHandleInput"]').simulate("blur");

    expect(onRename).not.toHaveBeenCalled();
  });

  it("names what this cell can read, under the box it would be typed in", () => {
    const line = shallow(
      <AvailableToRead
        canEdit
        available={[
          { name: "orders", columns: [{ name: "city" }] },
          { name: "by_city", columns: [] },
        ]}
      />
    );

    expect(line.find("code").map((one) => one.prop("children"))).toEqual(["orders", "by_city"]);
  });

  it("says nothing where there is nothing above to read", () => {
    expect(shallow(<AvailableToRead canEdit available={[]} />).isEmptyRender()).toBe(true);
  });

  it("completes against the cells above, not against a data source", () => {
    const available = [{ name: "orders", columns: [{ name: "city", type: "string" }] }];
    const page = mount(aCell({ source: "SELECT 1" }), { available });

    const editor = page.find("QueryEditor");
    expect(editor.prop("schema")).toEqual(available);
    expect(editor.prop("autocompleteEnabled")).toBe(true);
  });
});
