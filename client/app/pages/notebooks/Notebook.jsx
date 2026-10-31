import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import PropTypes from "prop-types";
import cx from "classnames";
import CaretRightOutlinedIcon from "@ant-design/icons/CaretRightOutlined";
import QuestionCircleOutlinedIcon from "@ant-design/icons/QuestionCircleOutlined";
import Alert from "antd/lib/alert";
import Button from "antd/lib/button";
import Dropdown from "antd/lib/dropdown";
import Menu from "antd/lib/menu";
import Tooltip from "antd/lib/tooltip";
import { map, reject, sortBy } from "lodash";

import Link from "@/components/Link";
import LoadingState from "@/components/items-list/components/LoadingState";
import notification from "@/services/notification";
import Notebook from "@/services/notebook";
import DataSource from "@/services/data-source";
import { fetchDataFromJob } from "@/services/query-result";

import NotebookCell from "./NotebookCell";
import NotebookScheduleDialog from "./NotebookScheduleDialog";
import EditableTitle from "./EditableTitle";
import ShareNotebookButton from "./ShareNotebookButton";
import NotebookHelpDialog from "./NotebookHelpDialog";
import "./notebook.less";

/*
  A notebook: a chain of cells, where everything else here ends in one SELECT.

  Two decisions on this page are the design rather than taste.

  **Nothing attaches an interpreter until somebody runs a Python cell.** The
  header says whether one is attached and offers to let it go; opening the page
  asks and never creates. A Spark session takes 30-60 seconds to come up, and a
  page that paid that on open would not feel like a BI tool however fast the
  rest of it is.

  **A run refetches the notebook.** Running a cell changes the cells *below*
  it -- they become stale, or newly runnable, or no longer able to read what
  they read. Patching one cell's result into place locally would leave every
  one of those stale on the screen while being right in the database.
*/
function NotebookPage({ notebookId }) {
  const [notebook, setNotebook] = useState(null);
  const [dataSources, setDataSources] = useState([]);
  const [loadError, setLoadError] = useState(null);
  const [running, setRunning] = useState(null);
  // What an export captures: the cells, not the page around them.
  const cellsRef = useRef(null);

  const load = useCallback(() => {
    return Notebook.get(notebookId)
      .then(setNotebook)
      .catch(() =>
        setLoadError("This notebook could not be opened. It may have been archived or is somebody's draft.")
      );
  }, [notebookId]);

  useEffect(() => {
    load();
    DataSource.query()
      .then(setDataSources)
      .catch(() => setDataSources([]));
  }, [load]);

  const cells = useMemo(() => sortBy(notebook ? notebook.cells : [], "position"), [notebook]);

  const onCellChanged = useCallback(
    (saved) => {
      // `null` means "something ran" -- reload, because the cells below this
      // one have changed even though nothing about them was edited.
      if (!saved) {
        return load();
      }
      setNotebook((current) =>
        current
          ? { ...current, cells: map(current.cells, (one) => (one.id === saved.id ? { ...one, ...saved } : one)) }
          : current
      );
      return Promise.resolve();
    },
    [load]
  );

  const onCellRemoved = useCallback((removed) => {
    setNotebook((current) =>
      current ? { ...current, cells: reject(current.cells, (one) => one.id === removed.id) } : current
    );
  }, []);

  const addCell = useCallback(
    (kind) => {
      Notebook.addCell(notebookId, { kind }).then(() => load());
    },
    [notebookId, load]
  );

  const detach = useCallback(() => {
    Notebook.detach(notebookId).then(({ detached }) => {
      notification.success(
        detached ? "The interpreter has been let go. Your variables went with it." : "No interpreter was attached."
      );
      load();
    });
  }, [notebookId, load]);

  const rename = useCallback(
    (name) => {
      if (!name) {
        // A notebook with no name is a row nobody can find again, so an
        // emptied box keeps what was there rather than saving nothing.
        return;
      }
      Notebook.save(notebookId, { name }).then(setNotebook);
    },
    [notebookId]
  );

  const publish = useCallback(() => {
    Notebook.save(notebookId, { is_draft: false }).then(setNotebook);
  }, [notebookId]);

  /*
    Run the whole chain.

    `running` is set to the string "all" rather than a cell id: every cell's
    Run is disabled while anything runs, and the page has one flag for that.
    A cell id would be a lie about which cell is going.
  */
  const runAll = useCallback(() => {
    setRunning("all");
    Notebook.runAll(notebookId)
      .then((response) => fetchDataFromJob(response.job.id))
      .then(() => notification.success("The notebook ran."))
      .catch((reason) => {
        const message = reason && reason.message ? reason.message : String(reason || "The notebook did not finish.");
        notification.error(message);
      })
      .finally(() => {
        setRunning(null);
        load();
      });
  }, [notebookId, load]);

  const schedule = useCallback(() => {
    NotebookScheduleDialog.showModal({ notebook }).onClose((wanted) =>
      Notebook.setSchedule(notebookId, wanted)
        .then((saved) => {
          setNotebook(saved);
          notification.success(wanted ? "This notebook will run on its schedule." : "The schedule has been removed.");
        })
        .catch((reason) => notification.error((reason && reason.message) || "That schedule could not be saved."))
    );
  }, [notebook, notebookId]);

  /*
    A PDF, by way of the browser's own print.

    Not the screenshots service: that is a Chromium container for alert
    images, it is off in most installs, and a notebook is a document --
    browsers paginate documents properly and already write PDF. The print
    stylesheet does the work, and it keeps whatever is folded folded, so the
    notebook you tidied is the report you get.
  */
  if (loadError) {
    return <Alert type="warning" showIcon message={loadError} className="notebook-load-error" />;
  }
  if (!notebook) {
    return <LoadingState className="" />;
  }

  const interpreterState = notebook.interpreter || { configured: false, attached: false };
  const sqlCellsOnly = !interpreterState.configured;

  const addMenu = (
    <Menu>
      <Menu.Item key="sql" onClick={() => addCell("sql")}>
        SQL cell — query a data source, or read earlier cells
      </Menu.Item>
      <Menu.Item key="python" onClick={() => addCell("python")} disabled={sqlCellsOnly}>
        Python cell
        {sqlCellsOnly ? " — needs an interpreter this install has not configured" : " — reshape an earlier cell"}
      </Menu.Item>
    </Menu>
  );

  return (
    <div className="notebook-page" data-test="NotebookPage">
      <div className="notebook-header">
        <div className="notebook-title">
          {/*
            Clicked to rename, the same way a cell is. A notebook called
            "New Notebook" six weeks later is the normal outcome of hiding
            renaming behind a settings dialog.
          */}
          <h3>
            <EditableTitle
              value={notebook.name}
              placeholder="Name this notebook"
              canEdit={notebook.can_edit}
              onChange={rename}
              className="notebook-name"
              inputClassName="notebook-name-input"
              dataTest="NotebookName"
            />
          </h3>
          {notebook.is_draft && <span className="notebook-draft">Draft</span>}
          {notebook.description && <p className="notebook-description">{notebook.description}</p>}
          <NotebookSize cells={cells} />
        </div>
        <span className="notebook-header-spacer" />
        <InterpreterState state={interpreterState} onDetach={detach} />
        {notebook.can_edit && cells.length > 0 && (
          <Tooltip title="Run every cell, in order. Stops at the first one that fails.">
            <Button
              size="small"
              icon={<CaretRightOutlinedIcon />}
              onClick={runAll}
              disabled={!!running}
              data-test="RunAll"
            >
              {running === "all" ? "Running…" : "Run all"}
            </Button>
          </Tooltip>
        )}
        <ShareNotebookButton notebook={notebook} getExportTarget={() => cellsRef.current} onChanged={load} />
        {notebook.can_edit && (
          <Tooltip title={describeSchedule(notebook)}>
            <Button size="small" onClick={schedule} data-test="ScheduleNotebook">
              {notebook.schedule ? "Scheduled" : "Schedule"}
            </Button>
          </Tooltip>
        )}
        {notebook.is_draft && notebook.can_edit && (
          <Button size="small" onClick={publish} data-test="PublishNotebook">
            Publish
          </Button>
        )}
        {notebook.can_edit && (
          <Dropdown overlay={addMenu} trigger={["click"]} placement="bottomRight">
            <Button size="small" type="primary" data-test="AddCell">
              Add cell
            </Button>
          </Dropdown>
        )}
        <Button
          size="small"
          type="text"
          icon={<QuestionCircleOutlinedIcon />}
          onClick={() => NotebookHelpDialog.showModal({})}
          data-test="NotebookHelp"
        >
          How notebooks work
        </Button>
        <Link href="notebooks" className="notebook-back">
          All notebooks
        </Link>
      </div>

      {/*
        What this is, for somebody who arrived from Queries and has no reason
        to guess. Three lines, on the page rather than in the docs: a feature
        nobody understands the point of is one nobody opens twice.

        Shown on an empty notebook, where somebody is deciding whether to
        bother, and dismissible everywhere else -- see NotebookList, which
        carries the same words for the same reason.
      */}
      {cells.length === 0 && (
        <Alert
          className="notebook-empty"
          type="info"
          showIcon
          message="A notebook is for work one SELECT cannot hold."
          description={
            <>
              <p>
                A query ends in one statement and a dashboard draws what it returned. A notebook chains steps: pull
                this, join it to that, reshape it in Python, look — each step named, so the next one can read it.
              </p>
              <p className="notebook-why-last">
                It keeps the data source permissions and the result store you already have, which is what people lose
                the moment they do this work in a notebook on their laptop instead.
              </p>
              <p className="notebook-why-last">
                Start with a SQL cell: a code cell cannot query, it reads what a SQL cell above it fetched.
              </p>
            </>
          }
        />
      )}

      <div className="notebook-body">
        <NotebookContents cells={cells} />

        <div className="notebook-cells" ref={cellsRef}>
          {map(cells, (cell) => (
            <div key={cell.id} id={`cell-${cell.id}`}>
              <NotebookCell
                cell={cell}
                notebookId={notebook.id}
                dataSources={dataSources}
                canEdit={notebook.can_edit}
                cluster={!!interpreterState.cluster}
                running={running}
                onRunningChanged={(busy) => setRunning(busy ? cell.id : null)}
                onChanged={onCellChanged}
                onRemoved={onCellRemoved}
              />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/*
  Jump to a cell.

  `scrollIntoView` alone was not enough, and the reason is the layout: the
  page does not scroll, `.application-layout-content` does -- it is the
  element with `overflow-y: auto`. So the scrollable ancestor is found and
  scrolled by hand, which also lets the cell be offset clear of the top
  edge rather than jammed against it.

  Falls back to `scrollIntoView` when no scrolling ancestor is found, which
  is what happens on the public page and in a test.
*/
export function scrollToCell(cellId) {
  const found = document.getElementById(`cell-${cellId}`);
  if (!found) {
    return;
  }
  let scroller = found.parentElement;
  while (scroller && scroller !== document.body) {
    const style = window.getComputedStyle(scroller);
    const scrolls = /(auto|scroll)/.test(style.overflowY);
    if (scrolls && scroller.scrollHeight > scroller.clientHeight) {
      const top = found.getBoundingClientRect().top - scroller.getBoundingClientRect().top + scroller.scrollTop;
      scroller.scrollTo({ top: top - 12, behavior: "smooth" });
      return;
    }
    scroller = scroller.parentElement;
  }
  found.scrollIntoView({ behavior: "smooth", block: "start" });
}

/*
  The contents, down the left.

  The single biggest reason a Zeppelin notebook of thirty cells is navigable
  and ours was not. Titles where somebody set one, names where they did not --
  a list reading `cell_1 … cell_30` would be a list nobody reads, which is why
  a cell can be titled at all.

  Hidden rather than empty below three cells: a contents list for two cells is
  furniture.
*/
export function NotebookContents({ cells }) {
  if (cells.length === 0) {
    return null;
  }
  return (
    <nav className="notebook-contents" data-test="NotebookContents" aria-label="Contents">
      <div className="notebook-contents-heading">Contents</div>
      <ol>
        {map(cells, (cell) => (
          <li key={cell.id}>
            <a
              href={`#cell-${cell.id}`}
              className={cx("notebook-contents-entry", `notebook-contents-${cell.kind}`, {
                "notebook-contents-folded": !!(cell.options || {}).collapsed,
              })}
              onClick={(e) => {
                e.preventDefault();
                scrollToCell(cell.id);
              }}
              data-test={`ContentsEntry-${cell.name}`}
            >
              {cell.title || cell.name}
            </a>
          </li>
        ))}
      </ol>
    </nav>
  );
}

NotebookContents.propTypes = {
  cells: PropTypes.arrayOf(PropTypes.object).isRequired,
};

/*
  How big this notebook is, and how much of the warehouse it touches.

  Data sources counted distinctly rather than per cell: eight cells against
  one warehouse is one source, and saying "8 data sources" would make a
  notebook look like it reaches further than it does. The same pair is shown
  on the list, so the list says something before anybody opens anything.
*/
export function countOf(cells) {
  const sources = new Set();
  cells.forEach((cell) => cell.data_source_id && sources.add(cell.data_source_id));
  return { cells: cells.length, dataSources: sources.size };
}

function plural(n, one, many) {
  return `${n} ${n === 1 ? one : many}`;
}

export function NotebookSize({ cells }) {
  const counted = countOf(cells);
  if (counted.cells === 0) {
    return null;
  }
  return (
    <span className="notebook-size" data-test="NotebookSize">
      {plural(counted.cells, "cell", "cells")} ·{" "}
      {counted.dataSources === 0
        ? "no data source"
        : plural(counted.dataSources, "data source", "data sources")}
    </span>
  );
}

NotebookSize.propTypes = {
  cells: PropTypes.arrayOf(PropTypes.object).isRequired,
};

/*
  The schedule in a sentence, for the tooltip.

  Says when it last ran as well as when it next will: a schedule that has
  never fired looks identical to one that is working until you can see that
  nothing has happened.
*/
export function describeSchedule(notebook) {
  if (!notebook.schedule) {
    return "This notebook runs only when somebody asks.";
  }
  const when = `Runs on \`${notebook.schedule}\`.`;
  if (notebook.schedule_failures > 0) {
    return `${when} The last run failed — it is being retried further apart until one works.`;
  }
  if (!notebook.last_scheduled_at) {
    return `${when} It has not run on its own yet.`;
  }
  return `${when} It last started on its own at ${new Date(notebook.last_scheduled_at).toLocaleString()}.`;
}

NotebookPage.propTypes = {
  notebookId: PropTypes.oneOfType([PropTypes.number, PropTypes.string]).isRequired,
};

/*
  Whether Python can run here, and whether it is running now.

  Three states, said plainly, because they lead to three different actions:
  not configured (ask an administrator, or use SQL cells), configured and
  attached (your variables are alive, and you may let them go), configured and
  not attached (the next Python run will attach, and will say how long that
  takes).
*/
export function InterpreterState({ state, onDetach }) {
  if (!state.configured) {
    return (
      <Tooltip title="Python cells need an interpreter. SQL cells work without one.">
        <span className="notebook-interpreter notebook-interpreter-off" data-test="InterpreterState">
          No interpreter
        </span>
      </Tooltip>
    );
  }
  if (!state.attached) {
    return (
      <Tooltip title="Opening a notebook attaches nothing. The first Python cell you run will attach one.">
        <span className="notebook-interpreter" data-test="InterpreterState">
          Interpreter ready
        </span>
      </Tooltip>
    );
  }
  return (
    <span className="notebook-interpreter notebook-interpreter-on" data-test="InterpreterState">
      Interpreter attached
      <Button size="small" type="text" onClick={onDetach} data-test="DetachInterpreter">
        Let go
      </Button>
    </span>
  );
}

InterpreterState.propTypes = {
  state: PropTypes.object.isRequired,
  onDetach: PropTypes.func.isRequired,
};

export default NotebookPage;
