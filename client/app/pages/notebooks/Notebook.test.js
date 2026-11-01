import React from "react";
import { shallow, mount } from "enzyme";
import { act } from "react-dom/test-utils";
import NotebookPage, {
  InterpreterState,
  NotebookContents,
  NotebookSize,
  countOf,
  describeSchedule,
  scrollToCell,
} from "./Notebook";
import { NotebookScheduleDialog, matchingPreset } from "./NotebookScheduleDialog";

// A factory inside the mock would be an out-of-scope reference, which jest
// refuses: each test supplies what `get` should answer with.
jest.mock("@/services/notebook", () => ({
  get: jest.fn(() => Promise.resolve({})),
  handoffs: jest.fn(() => Promise.resolve({ handoffs: [] })),
  addCell: jest.fn(() => Promise.resolve({})),
  detach: jest.fn(() => Promise.resolve({ detached: true })),
  save: jest.fn(() => Promise.resolve({})),
  runAll: jest.fn(() => Promise.resolve({ job: { id: "j1" } })),
  setSchedule: jest.fn(() => Promise.resolve({})),
  share: jest.fn(() => Promise.resolve({ public_url: "http://x/notebooks/public/abc" })),
  unshare: jest.fn(() => Promise.resolve({ public_url: null })),
}));
jest.mock("@/services/query-result", () => ({ fetchDataFromJob: jest.fn(() => Promise.resolve(1)) }));
jest.mock("@/services/data-source", () => ({ query: jest.fn(() => Promise.resolve([])) }));
jest.mock("@/services/notification", () => ({ success: jest.fn(), warning: jest.fn(), error: jest.fn() }));
jest.mock("./NotebookCell", () => function NotebookCell() {
  return null;
});

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

    // Read off the rendered text rather than the prop: the description is
    // several paragraphs now, and a prop assertion would only have been
    // checking that it is still a string.
    expect(page.find("Alert.notebook-empty").text()).toContain("cannot query");
  });

  it("says what a notebook is for, to somebody who arrived from Queries", async () => {
    const page = await open(fixture({ cells: [] }));
    const said = page.find("Alert.notebook-empty").text();

    expect(said).toContain("one SELECT cannot hold");
    // The sentence that is the actual argument for using it rather than a
    // notebook on somebody's laptop.
    expect(said).toContain("permissions");
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
    // PlainButton is a forwardRef, so it has no display name to find it by.
    const entries = contents.find(".notebook-contents-entry").map((one) => one.prop("children"));

    expect(entries).toEqual(["Orders", "code_1", "Takings"]);
  });

  it("jumps to the cell rather than navigating to it", () => {
    // A button, not a link: `handleNavigationIntent` takes any <a href> and
    // hands it to the router without looking at `defaultPrevented`, so an
    // anchor here navigated away from the page instead of scrolling it.
    const contents = shallow(<NotebookContents cells={cells} />);
    const entry = contents.find('[data-test="ContentsEntry-cell_1"]');

    expect(entry.prop("href")).toBeUndefined();
    expect(typeof entry.prop("onClick")).toBe("function");
  });

  it("marks a folded cell as put away rather than dropping it", () => {
    const folded = [...cells.slice(0, 2), { ...cells[2], options: { collapsed: true } }];
    const contents = shallow(<NotebookContents cells={folded} />);

    expect(contents.find('[data-test="ContentsEntry-cell_2"]').hasClass("notebook-contents-folded")).toBe(true);
  });

  it("is drawn as soon as there is a cell", () => {
    // A notebook somebody has just started is exactly when they are least
    // sure what goes where, so the contents appear with the first cell.
    expect(shallow(<NotebookContents cells={cells.slice(0, 1)} />).isEmptyRender()).toBe(false);
  });

  it("is not drawn for a notebook with nothing in it", () => {
    expect(shallow(<NotebookContents cells={[]} />).isEmptyRender()).toBe(true);
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

/*
  The schedule, said in words.

  A schedule that has never fired looks identical to one that is working
  until the page says so -- which is the failure mode worth guarding, because
  the whole point of a schedule is that nobody is watching it.
*/
describe("describing a schedule", () => {
  it("says so when there is none", () => {
    expect(describeSchedule({ schedule: null })).toContain("only when somebody asks");
  });

  it("carries the expression, so it can be checked", () => {
    expect(describeSchedule({ schedule: "0 6 * * *" })).toContain("0 6 * * *");
  });

  it("admits when it has never run on its own", () => {
    const said = describeSchedule({ schedule: "0 6 * * *", last_scheduled_at: null });

    expect(said).toContain("not run on its own yet");
  });

  it("says when it last started", () => {
    const said = describeSchedule({ schedule: "0 6 * * *", last_scheduled_at: "2026-10-30T06:00:00Z" });

    expect(said).toContain("last started");
  });

  it("says a failing schedule is backing off, which is why it looks quiet", () => {
    const said = describeSchedule({ schedule: "0 6 * * *", schedule_failures: 3, last_scheduled_at: "x" });

    expect(said).toContain("failed");
    expect(said).toContain("further apart");
  });
});

describe("the schedule dialog", () => {
  function dialogFor(notebook) {
    return shallow(
      <NotebookScheduleDialog dialog={{ props: {}, close: jest.fn(), dismiss: jest.fn() }} notebook={notebook} />
    );
  }

  it("preselects the preset a saved schedule matches", () => {
    const made = dialogFor({ schedule: "0 6 * * *" });

    expect(made.find(".notebook-schedule-choices").prop("value")).toBe("0 6 * * *");
  });

  it("falls back to the cron box for an expression no preset covers", () => {
    const made = dialogFor({ schedule: "*/7 2 * * *" });

    expect(made.find(".notebook-schedule-choices").prop("value")).toBe("custom");
    expect(made.find('[data-test="ScheduleCronInput"]').prop("value")).toBe("*/7 2 * * *");
  });

  it("starts on 'only when asked' for a notebook with no schedule", () => {
    expect(dialogFor({ schedule: null }).find(".notebook-schedule-choices").prop("value")).toBe("");
  });

  it("will not let a draft be scheduled", () => {
    const made = dialogFor({ schedule: null, is_draft: true });

    expect(made.find('[data-test="ScheduleNeedsPublishing"]').exists()).toBe(true);
    expect(made.find("Modal").prop("okButtonProps").disabled).toBe(true);
  });

  it("matchingPreset only claims a match that is exact", () => {
    expect(matchingPreset("0 6 * * *")).toBe("0 6 * * *");
    expect(matchingPreset("0 6 * * 1")).toBe("custom");
  });
});

/*
  Running the whole thing, printing it, and handing it to somebody.

  Three buttons with three different audiences: Run all is for the author,
  PDF is for whoever gets sent the report, and Share is for whoever has no
  account at all.
*/
describe("the header's actions", () => {
  beforeEach(() => jest.clearAllMocks());

  it("offers Run all once there is something to run", async () => {
    const page = await open(fixture());

    expect(page.find('[data-test="RunAll"]').exists()).toBe(true);
  });

  it("does not offer Run all on an empty notebook", async () => {
    const page = await open(fixture({ cells: [] }));

    expect(page.find('[data-test="RunAll"]').exists()).toBe(false);
  });

  it("runs every cell as one job, not one call per cell", async () => {
    const page = await open(fixture());

    await act(async () => {
      page.find('[data-test="RunAll"]').first().simulate("click");
    });

    expect(Notebook.runAll).toHaveBeenCalledWith(5);
    expect(Notebook.runAll).toHaveBeenCalledTimes(1);
  });

  it("puts everything that hands this notebook to somebody behind one button", async () => {
    // The dashboard's shape: a link, a PDF and an image in one menu, rather
    // than a row of buttons that each do a bit of sharing.
    const page = await open(fixture());

    expect(page.find('[data-test="ShareNotebook"]').exists()).toBe(true);
  });

  it("offers sharing to a reader too, because reading is not editing", async () => {
    const page = await open(fixture({ can_edit: false }));

    expect(page.find('[data-test="ShareNotebook"]').exists()).toBe(true);
  });

  it("captures the cells, not the page around them", async () => {
    // No header, no navigation, and folded cells stay folded -- a notebook
    // somebody tidied is the report they meant to send.
    const page = await open(fixture());
    const target = page.find("ShareNotebookButton").prop("getExportTarget")();

    expect(target.className).toContain("notebook-cells");
  });

  it("lets the notebook be renamed by clicking its name", async () => {
    const page = await open(fixture({ name: "Quarter" }));

    await act(async () => {
      page.find('[data-test="NotebookName"]').first().simulate("click");
    });
    page.update();
    // `find` twice without an update in between hands the second call a
    // stale element, whose blur commits the draft as it was before the
    // change -- which equals the old name, so nothing is saved and the test
    // passes or fails for the wrong reason.
    await act(async () => {
      page.find("input.notebook-name-input").simulate("change", { target: { value: "Quarterly rollup" } });
    });
    page.update();
    await act(async () => {
      page.find("input.notebook-name-input").simulate("blur");
    });

    expect(Notebook.save).toHaveBeenCalledWith(5, { name: "Quarterly rollup" });
  });

  it("keeps the old name when the box is emptied", async () => {
    // A notebook with no name is a row nobody finds again.
    const page = await open(fixture({ name: "Quarter" }));

    await act(async () => {
      page.find('[data-test="NotebookName"]').first().simulate("click");
    });
    page.update();
    await act(async () => {
      page.find("input.notebook-name-input").simulate("change", { target: { value: "   " } });
    });
    page.update();
    await act(async () => {
      page.find("input.notebook-name-input").simulate("blur");
    });

    expect(Notebook.save).not.toHaveBeenCalled();
  });
});

/*
  Jumping to a cell.

  `scrollIntoView` alone did nothing in the real app, and the reason is the
  layout: the page does not scroll, `.application-layout-content` does. The
  contents list is the whole reason a cell can be titled, so a contents list
  that does not move the page is the feature not working.
*/
describe("jumping to a cell", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  function pageWith({ scrolls }) {
    document.body.innerHTML = `
      <div id="scroller" style="${scrolls ? "overflow-y: auto;" : ""}">
        <div id="cell-7"></div>
      </div>`;
    const scroller = document.getElementById("scroller");
    // jsdom lays nothing out, so the heights that decide "is this the
    // scrolling ancestor" are supplied here.
    Object.defineProperty(scroller, "scrollHeight", { value: scrolls ? 2000 : 10, configurable: true });
    Object.defineProperty(scroller, "clientHeight", { value: 500, configurable: true });
    scroller.scrollTo = jest.fn();
    return scroller;
  }

  it("scrolls the element that actually scrolls, not the window", () => {
    const scroller = pageWith({ scrolls: true });

    scrollToCell(7);

    expect(scroller.scrollTo).toHaveBeenCalled();
    expect(scroller.scrollTo.mock.calls[0][0].behavior).toBe("smooth");
  });

  it("falls back to scrollIntoView when nothing above it scrolls", () => {
    pageWith({ scrolls: false });
    const target = document.getElementById("cell-7");
    target.scrollIntoView = jest.fn();

    scrollToCell(7);

    expect(target.scrollIntoView).toHaveBeenCalled();
  });

  it("does nothing, rather than throwing, for a cell that is not on the page", () => {
    pageWith({ scrolls: true });

    expect(() => scrollToCell(999)).not.toThrow();
  });
});

/*
  Which names a cell may read.

  Downward references do not resolve, so a cell is offered only what the cells
  *above* it handed over -- completing anything else would be the editor
  suggesting a mistake. Fetched after the notebook rather than with it:
  reading it opens the notebook's DuckDB file, and that is the mistake
  `reaches_a_cluster` already made on this page once.
*/
describe("what a cell is allowed to read", () => {
  beforeEach(() => jest.clearAllMocks());

  it("asks for the handoffs after the notebook, not as part of it", async () => {
    await open();

    expect(Notebook.handoffs).toHaveBeenCalledWith(5);
  });

  it("offers each cell only the cells above it", async () => {
    Notebook.handoffs.mockResolvedValueOnce({
      handoffs: [
        { name: "orders", position: 0, columns: [{ name: "city" }] },
        { name: "by_city", position: 1, columns: [] },
      ],
    });
    const page = await open(
      fixture({
        cells: [
          { id: 1, name: "orders", kind: "sql", position: 0, source: "SELECT 1", options: {} },
          { id: 2, name: "by_city", kind: "sql", position: 1, source: "SELECT 2", options: {} },
          { id: 3, name: "cell_3", kind: "python", position: 2, source: "by_city", options: {} },
        ],
      })
    );
    await act(async () => {});
    page.update();

    const offered = page.find("NotebookCell").map((one) => one.prop("available").map((each) => each.name));
    expect(offered).toEqual([[], ["orders"], ["orders", "by_city"]]);
  });

  it("still opens when the notebook will not say what it handed over", async () => {
    Notebook.handoffs.mockRejectedValueOnce(new Error("locked"));
    const page = await open();
    await act(async () => {});
    page.update();

    expect(page.find('[data-test="NotebookName"]').text()).toBe("Quarter");
    expect(page.find("NotebookCell").first().prop("available")).toEqual([]);
  });
});
