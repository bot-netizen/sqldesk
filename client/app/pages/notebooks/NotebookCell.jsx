import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import PropTypes from "prop-types";
import cx from "classnames";
import Alert from "antd/lib/alert";
import Button from "antd/lib/button";
import Select from "antd/lib/select";
import Tooltip from "antd/lib/tooltip";
import Table from "antd/lib/table";
import Tabs from "antd/lib/tabs";
import LoadingOutlinedIcon from "@ant-design/icons/LoadingOutlined";
import PlusOutlinedIcon from "@ant-design/icons/PlusOutlined";
import CloseOutlinedIcon from "@ant-design/icons/CloseOutlined";
import { map, size } from "lodash";

import Dropdown from "antd/lib/dropdown";
import Menu from "antd/lib/menu";
import CodeOutlinedIcon from "@ant-design/icons/CodeOutlined";
import TableOutlinedIcon from "@ant-design/icons/TableOutlined";
import DownloadOutlinedIcon from "@ant-design/icons/DownloadOutlined";
import MoreOutlinedIcon from "@ant-design/icons/MoreOutlined";
import CaretRightOutlinedIcon from "@ant-design/icons/CaretRightOutlined";
import PauseOutlinedIcon from "@ant-design/icons/PauseOutlined";
import DownOutlinedIcon from "@ant-design/icons/DownOutlined";
import RightOutlinedIcon from "@ant-design/icons/RightOutlined";

import PlainButton from "@/components/PlainButton";
import { getEditorComponents } from "@/components/queries/editor-components";
import Notebook from "@/services/notebook";
import CellVisualizationDialog from "./CellVisualizationDialog";
import CellFigure from "./CellFigure";
import EditableTitle from "./EditableTitle";
import popupInPage from "./popup";
import { Renderer } from "@/components/visualizations/visualizationComponents";
import { fetchDataFromJob } from "@/services/query-result";
import notification from "@/services/notification";

/*
  One cell: its code, what it is allowed to do, and what it produced.

  Three things on this component are the design rather than decoration.

  **The reason a cell cannot run comes from the server** (`cannot_run`), and it
  is shown before anybody presses Run. Zeppelin's failure mode is discovering
  the limits by hitting them, and these limits need the install's settings and
  the other cells' state to work out -- so deriving them again here would be a
  second copy of the rules.

  **Stale is shown and never fixed.** If this cell read `orders` and `orders`
  has re-run since, the number here is the number that was computed, from data
  that has moved on. Re-running is the reader's decision; replacing it quietly
  is how a notebook lies.

  **A dataframe and a printout are different things.** A cell that produced a
  table can be read by a later cell; one that produced text cannot, and the
  page says which this is rather than leaving somebody to find out by writing
  a reference that will not resolve.
*/

//: The three things a cell can run on, as the "Runs on" control values.
//: Prefixed rather than bare ids so one control can carry both a warehouse
//: and a kind without the two being confusable.
const EARLIER_CELLS = "cells";
const PYTHON = "python";
const SOURCE_PREFIX = "source:";

export default function NotebookCell({
  cell,
  notebookId,
  dataSources,
  canEdit,
  cluster,
  available,
  onChanged,
  onRemoved,
  running,
  onRunningChanged,
}) {
  const [source, setSource] = useState(cell.source || "");
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  // When the run on screen began, so the header can say how long it has been
  // going. Local to this browser: the server does not report a start time for
  // a cell somebody else set running.
  const [startedAt, setStartedAt] = useState(null);
  // Started from the overflow menu rather than by clicking the handle: one
  // click on the handle copies it, which is what somebody about to write the
  // next cell wants, and renaming is the rarer thing.
  const [renaming, setRenaming] = useState(false);
  const latestResultId = cell.latest_result_id;
  // The editor is chosen by the cell's language, not by the data source: a
  // Python cell has no data source at all.
  const { QueryEditor } = useMemo(() => getEditorComponents(null), []);
  const mounted = useRef(true);

  useEffect(() => () => (mounted.current = false), []);
  useEffect(() => setSource(cell.source || ""), [cell.id, cell.source]);

  /*
    The saved output, fetched per cell.

    Through the notebook rather than through a query, because a cell has no
    query id -- and the data source's own permission is checked at that
    endpoint, so a reader who may open a published notebook but was never
    allowed that warehouse is refused the rows rather than the page.
  */
  useEffect(() => {
    if (!latestResultId) {
      setResult(null);
      return undefined;
    }
    let live = true;
    Notebook.cellResult(notebookId, cell.id)
      .then((found) => live && setResult(found))
      .catch(() => live && setResult(null));
    return () => {
      live = false;
    };
  }, [latestResultId, notebookId, cell.id]);

  const save = useCallback(
    (changes) => {
      if (!canEdit) {
        return Promise.resolve(cell);
      }
      return Notebook.saveCell(notebookId, cell.id, changes).then((saved) => {
        onChanged(saved);
        return saved;
      });
    },
    [canEdit, notebookId, cell, onChanged]
  );

  const run = useCallback(() => {
    setError(null);
    setBusy(true);
    setStartedAt(Date.now());
    onRunningChanged(true);
    // Saved first, so what runs is what is on the screen. A cell whose text
    // only reached the server on blur would run its previous version, which is
    // the single most confusing thing a notebook can do.
    const started = source !== cell.source ? save({ source }) : Promise.resolve(cell);
    started
      .then(() => Notebook.runCell(notebookId, cell.id))
      .then((response) => fetchDataFromJob(response.job.id))
      .then(() => onChanged(null))
      .catch((reason) => {
        const message = reason && reason.message ? reason.message : String(reason || "This cell failed.");
        setError(message);
      })
      .finally(() => {
        if (mounted.current) {
          setBusy(false);
          setStartedAt(null);
          onRunningChanged(false);
        }
      });
  }, [source, cell, notebookId, save, onChanged, onRunningChanged]);

  const stop = useCallback(() => {
    Notebook.stop(notebookId).then(({ stopped }) => {
      if (!stopped) {
        notification.warning("There was no cell running to stop.");
      }
    });
  }, [notebookId]);

  /*
    The chart editor, on this cell's own output.

    Opened with the rows that are on the page -- the truncated slice, not the
    whole handoff. That is what a chart should be drawn from anyway: a chart of
    four million points is a smear, and the editor would have to pull all of
    them through the browser to make it.
  */
  const visualize = useCallback(() => {
    const data = (result && result.data) || null;
    if (!data) {
      return;
    }
    CellVisualizationDialog.showModal({ cell, data }).onClose((visualization) =>
      save({ options: { ...(cell.options || {}), visualization } })
    );
  }, [cell, result, save]);

  const removeChart = useCallback(() => {
    save({ options: { ...(cell.options || {}), visualization: null } });
  }, [cell, save]);

  const remove = useCallback(() => {
    Notebook.deleteCell(notebookId, cell.id).then(() => onRemoved(cell));
  }, [notebookId, cell, onRemoved]);

  /*
    How this cell is shown, kept on the cell rather than in the browser.

    Zeppelin does the same, and it is the right call for the same reason:
    somebody who folds a notebook into a readable report has done work, and
    that work is for whoever opens it next -- not only for their own browser.
  */
  const setOption = useCallback((changes) => save({ options: { ...(cell.options || {}), ...changes } }), [cell, save]);

  const collapsed = !!(cell.options || {}).collapsed;
  const hideCode = !!(cell.options || {}).hideCode;
  const hideOutput = !!(cell.options || {}).hideOutput;
  const produced = (cell.options || {}).produced;

  /*
    What a cell can do that is not wanted often enough to spend a slot on.

    Remove is here because deleting the cell every other cell below refers
    to should take two clicks, not one next to Run.
  */
  const moreMenu = (
    <Menu>
      {produced === "table" && result && (
        <Menu.Item key="chart" onClick={visualize} data-test="VisualizeCell">
          {(cell.options || {}).visualization ? "Edit the chart" : "Add a chart"}
        </Menu.Item>
      )}
      <Menu.Item key="rename" onClick={() => setRenaming(true)} data-test="RenameHandle">
        Rename what cells below call it
      </Menu.Item>
      <Menu.Item key="remove" danger onClick={remove} data-test="RemoveCell">
        Remove this cell
      </Menu.Item>
    </Menu>
  );

  /*
    The refusal, as it applies to what is on the screen rather than to what is
    saved. A cell saves when the editor loses focus, so somebody who has just
    typed into an empty cell would otherwise be told it is empty, with Run
    disabled, until they clicked somewhere else.
  */
  const typedSomething = !!(source || "").trim();
  const blocked = cell.cannot_run && !(cell.cannot_run_code === "empty" && typedSomething);
  const notice = blocked ? cell.cannot_run : null;

  const stale = cell.stale_because_of || [];
  const missing = cell.missing_inputs || [];

  return (
    <div className={cx("notebook-cell", `notebook-cell-${cell.kind}`)} data-test={`NotebookCell-${cell.name}`}>
      <div className="notebook-cell-header">
        <Tooltip title={collapsed ? "Show this cell" : "Fold this cell away"}>
          <Button
            size="small"
            type="text"
            className="notebook-cell-fold"
            onClick={() => setOption({ collapsed: !collapsed })}
            icon={collapsed ? <RightOutlinedIcon /> : <DownOutlinedIcon />}
            data-test="CollapseCell"
            aria-expanded={!collapsed}
            aria-label={collapsed ? "Show this cell" : "Fold this cell away"}
          />
        </Tooltip>
        <CellTitle
          cell={cell}
          canEdit={canEdit}
          onChange={(title) => title !== (cell.title || "") && save({ title })}
        />
        <CellHandle
          cell={cell}
          canEdit={canEdit}
          editing={renaming}
          onEditing={setRenaming}
          onRename={(name) => save({ name })}
        />

        <span className="notebook-cell-spacer" />
        {/*
          Beside Run, not beside the title: choosing where a cell runs and
          running it are the same moment, and on the left it read as part of
          the name.
        */}
        <RunsOn cell={cell} dataSources={dataSources} canEdit={canEdit} cluster={cluster} onChange={save} />
        {busy || running === cell.id ? (
          <>
            <RunningFor since={startedAt} />
            <Button
              size="small"
              className="notebook-cell-run"
              icon={<PauseOutlinedIcon />}
              onClick={stop}
              data-test="StopCell"
              aria-label="Stop this cell"
            />
          </>
        ) : (
          <Tooltip title={notice}>
            <Button
              size="small"
              type="primary"
              className="notebook-cell-run"
              icon={<CaretRightOutlinedIcon />}
              onClick={run}
              disabled={!!blocked || !!running}
              data-test="RunCell"
              aria-label="Run this cell"
            />
          </Tooltip>
        )}
        {/*
          Icons, not words.

          Five labelled controls per cell is most of a cell header, and on a
          notebook of thirty cells it is most of the page. Run keeps its word
          because it is the one somebody looks for; the rest are icons with
          tooltips, and the two that are rarely wanted sit under a menu.

          Code and output hide separately, which is the point of having both:
          reading a finished notebook and writing one want opposite things on
          screen -- somebody presenting a result wants the SQL gone, somebody
          debugging wants the table gone and the query in front of them.
        */}
        {!collapsed && (
          <Tooltip title={hideCode ? "Show the code" : "Hide the code"}>
            <Button
              size="small"
              type="text"
              className="notebook-cell-icon"
              icon={<CodeOutlinedIcon />}
              onClick={() => setOption({ hideCode: !hideCode })}
              data-test="ToggleCode"
              aria-pressed={!hideCode}
              aria-label={hideCode ? "Show the code" : "Hide the code"}
            />
          </Tooltip>
        )}
        {!collapsed && cell.last_run_at && (
          <Tooltip title={hideOutput ? "Show the output" : "Hide the output"}>
            <Button
              size="small"
              type="text"
              className="notebook-cell-icon"
              icon={<TableOutlinedIcon />}
              onClick={() => setOption({ hideOutput: !hideOutput })}
              data-test="ToggleOutput"
              aria-pressed={!hideOutput}
              aria-label={hideOutput ? "Show the output" : "Hide the output"}
            />
          </Tooltip>
        )}
        {/*
          The whole result, for somebody moving data rather than looking at
          it. Only on a cell that produced a relation: there is nothing to
          take out of a cell that printed.
        */}
        {!collapsed && produced === "table" && cell.last_run_at && (
          <Tooltip title="Download every row — not the slice shown here.">
            <a
              className="notebook-cell-icon notebook-cell-download"
              href={Notebook.downloadUrl(notebookId, cell.id)}
              download
              data-test="DownloadCell"
              aria-label="Download every row"
            >
              <DownloadOutlinedIcon />
            </a>
          </Tooltip>
        )}
        {canEdit && (
          <Dropdown overlay={moreMenu} trigger={["click"]} placement="bottomRight" getPopupContainer={popupInPage}>
            <Button
              size="small"
              type="text"
              className="notebook-cell-icon"
              icon={<MoreOutlinedIcon />}
              data-test="CellMenu"
              aria-label="More for this cell"
            />
          </Dropdown>
        )}
      </div>

      {/*
        Folded, the header is the whole cell. The notices below are deliberately
        folded away with it: a cell somebody has put out of sight is not a cell
        they want warnings from, and the contents list still carries it.
      */}
      {collapsed && (
        <div className="notebook-cell-folded" data-test="CellFolded">
          {summarise(cell, produced)}
        </div>
      )}

      {!collapsed && notice && (
        <Alert className="notebook-cell-notice" type="info" showIcon message={notice} data-test="CannotRun" />
      )}
      {!collapsed && missing.length > 0 && (
        <Alert
          className="notebook-cell-notice"
          type="error"
          showIcon
          message={`${missing.join(", ")} ${missing.length === 1 ? "no longer exists" : "no longer exist"}, so this cell cannot be reproduced.`}
          data-test="MissingInputs"
        />
      )}
      {!collapsed && stale.length > 0 && (
        <Alert
          className="notebook-cell-notice"
          type="warning"
          showIcon
          message={`${stale.join(", ")} ${stale.length === 1 ? "has" : "have"} run since this did, so what is below was computed from older data.`}
          data-test="Stale"
        />
      )}

      {!collapsed && !hideCode && (
        <>
          {/*
            Autocomplete on, and completing against the cells above rather
            than a data source's schema. This is the answer to the only
            question a notebook raises that a query does not -- *how do I get
            at cell three's data?* -- given where it is asked: type in cell
            four and `orders` comes up, with its columns under it.
          */}
          <QueryEditor
            className="notebook-cell-editor"
            syntax={cell.kind === "python" ? "python" : "sql"}
            value={source}
            onChange={setSource}
            onBlur={() => source !== cell.source && save({ source })}
            autocompleteEnabled
            schema={available}
          />
          <AvailableToRead available={available} canEdit={canEdit} />
        </>
      )}

      {!collapsed && error && (
        <Alert className="notebook-cell-notice" type="error" showIcon message={error} data-test="CellError" />
      )}
      {!collapsed && !hideOutput && cell.last_run_at && !error && (
        <CellOutput
          cell={cell}
          produced={produced}
          result={result}
          onRemoveChart={removeChart}
          onAddVisualization={canEdit ? visualize : null}
          onResizeChart={canEdit ? (chartHeight) => setOption({ chartHeight }) : null}
          onResizeTable={canEdit ? (tableHeight) => setOption({ tableHeight }) : null}
          onResizeFigure={canEdit ? (figureHeight) => setOption({ figureHeight }) : null}
        />
      )}
    </div>
  );
}

NotebookCell.propTypes = {
  cell: PropTypes.object.isRequired,
  notebookId: PropTypes.oneOfType([PropTypes.number, PropTypes.string]).isRequired,
  dataSources: PropTypes.arrayOf(PropTypes.object),
  canEdit: PropTypes.bool,
  cluster: PropTypes.bool,
  // What the cells above this one handed over, as the editor's schema:
  // `[{name, columns: [{name, type}]}]`.
  available: PropTypes.arrayOf(PropTypes.object),
  onChanged: PropTypes.func.isRequired,
  onRemoved: PropTypes.func.isRequired,
  running: PropTypes.oneOfType([PropTypes.number, PropTypes.string]),
  onRunningChanged: PropTypes.func.isRequired,
};

NotebookCell.defaultProps = {
  dataSources: [],
  canEdit: false,
  cluster: false,
  available: [],
  running: null,
};

/*
  What this cell runs on: a warehouse, the cells above it, or Python.

  One control rather than two, because they are one decision. The old page
  had the kind fixed at Add-cell time and a separate data source dropdown
  beside it, which left somebody looking at a Python cell wondering what the
  empty dropdown next to it meant -- the answer being that it did not apply.

  So the groups are the separation: pick anything under Python and the
  warehouses are visibly not in play. The line under the control says it in
  words, because a grouped dropdown is only obvious while it is open.
*/
export function RunsOn({ cell, dataSources, canEdit, cluster, onChange }) {
  const value =
    cell.kind === "python" ? PYTHON : cell.data_source_id ? `${SOURCE_PREFIX}${cell.data_source_id}` : EARLIER_CELLS;

  const change = useCallback(
    (picked) => {
      if (picked === PYTHON) {
        return onChange({ kind: "python", data_source_id: null });
      }
      if (picked === EARLIER_CELLS) {
        return onChange({ kind: "sql", data_source_id: null });
      }
      return onChange({ kind: "sql", data_source_id: Number(picked.slice(SOURCE_PREFIX.length)) });
    },
    [onChange]
  );

  // A cell may point at a data source this person is not allowed to see --
  // somebody else built the notebook, or their access was taken away. Without
  // an option to match, the control falls back to showing the raw value
  // (`source:3`), so it carries one of its own that cannot be chosen.
  const unseen = !!cell.data_source_id && !(dataSources || []).some((one) => one.id === cell.data_source_id);

  if (!canEdit) {
    return (
      <span className="notebook-cell-runs-on-static" data-test="RunsOn">
        {describeWhatItRunsOn(cell, dataSources, cluster)}
      </span>
    );
  }

  return (
    <span className="notebook-cell-runs-on" data-test="RunsOn">
      {/*
        The control says what the cell runs on, so nothing beside it needs to
        say it again. There was a sentence here repeating the chosen value in
        longer words, on every cell of every notebook.
      */}
      <Select
        size="small"
        value={value}
        onChange={change}
        className="notebook-cell-runs-on-select"
        dropdownMatchSelectWidth={false}
        getPopupContainer={popupInPage}
      >
        <Select.OptGroup label="Query a data source">
          {map(dataSources, (source) => (
            <Select.Option key={source.id} value={`${SOURCE_PREFIX}${source.id}`}>
              {source.name}
            </Select.Option>
          ))}
          {unseen && (
            <Select.Option key="unseen" value={`${SOURCE_PREFIX}${cell.data_source_id}`} disabled>
              A data source you cannot see
            </Select.Option>
          )}
        </Select.OptGroup>
        <Select.OptGroup label="Stay in this notebook">
          <Select.Option value={EARLIER_CELLS}>SQL over earlier cells</Select.Option>
        </Select.OptGroup>
        <Select.OptGroup label="Run Python — no data source">
          <Select.Option value={PYTHON}>{cluster ? "Python, with the Spark cluster" : "Python"}</Select.Option>
        </Select.OptGroup>
      </Select>
    </span>
  );
}

RunsOn.propTypes = {
  cell: PropTypes.object.isRequired,
  dataSources: PropTypes.arrayOf(PropTypes.object),
  canEdit: PropTypes.bool,
  cluster: PropTypes.bool,
  onChange: PropTypes.func.isRequired,
};

RunsOn.defaultProps = { dataSources: [], canEdit: false, cluster: false };

/*
  The same decision in words, for somebody who has no control to read it off.

  Only for a reader. An editor has the control itself, and a sentence beside
  it saying the same thing in longer words was on every cell of every
  notebook -- which is the sort of thing that reads as helpful once and as
  noise thereafter.

  Worded as the control's own options are, so the two cannot drift into
  describing the same cell differently.
*/
export function describeWhatItRunsOn(cell, dataSources, cluster) {
  if (cell.kind === "python") {
    return cluster ? "Python, with the Spark cluster" : "Python";
  }
  if (!cell.data_source_id) {
    return "SQL over earlier cells";
  }
  const source = (dataSources || []).find((one) => one.id === cell.data_source_id);
  return source ? `SQL against ${source.name}` : "SQL against a data source you cannot see";
}

/*
  What a person calls this step.

  Edited in place rather than behind a dialog: a title nobody can be bothered
  to set is a contents list reading `cell_1 … cell_30`, and a dialog is enough
  friction to cause exactly that. Falls back to the cell's name, which is
  always there.

  The handle sits beside it (see `CellHandle`), because the name is what later
  cells are written against -- somebody who titles a cell "Orders, cleaned"
  still needs to know they type `orders_cleaned` to read it. Titling a cell
  whose handle nobody has chosen and nothing yet reads renames the handle to
  match, so in the ordinary case there is only ever one thing to fill in.
*/
export function CellTitle({ cell, canEdit, onChange }) {
  return (
    <EditableTitle
      value={cell.title || ""}
      placeholder="Name this step"
      canEdit={canEdit}
      onChange={onChange}
      className="notebook-cell-title"
      inputClassName="notebook-cell-title-input"
      dataTest="CellTitle"
    />
  );
}

CellTitle.propTypes = {
  cell: PropTypes.object.isRequired,
  canEdit: PropTypes.bool,
  onChange: PropTypes.func.isRequired,
};

CellTitle.defaultProps = { canEdit: false };

/*
  What the cells below call this one.

  The one thing a notebook has that a query does not is that cell four can
  read cell three -- and the only way anybody finds that out is if the name to
  type is on the screen. Hiding it, which is what showing only the title did,
  left the mechanism with no visible handle at all: the rule was in the help
  dialog and nowhere a person actually was.

  So it is here, in monospace, looking like the identifier it is. **One click
  copies it**, because the next thing somebody does with it is paste it into
  the cell below; renaming is in the overflow menu, being much the rarer
  thing. A reader gets the chip too -- somebody reading a shared notebook is
  often somebody about to write a cell of their own.
*/
export function CellHandle({ cell, canEdit, editing, onEditing, onRename }) {
  const [draft, setDraft] = useState(cell.name);
  // Escape has to win against blur, and blur fires first. A flag rather than
  // ordering: `setDraft` has not landed by the time the blur handler reads it,
  // so resetting the draft and relying on it is a rename to the old value.
  const abandoned = useRef(false);

  useEffect(() => setDraft(cell.name), [cell.name]);

  const copy = useCallback(() => {
    const said = `Cells below this one read it as ${cell.name}.`;
    // The clipboard is missing on older browsers, on an insecure origin, and
    // in jsdom. The feature check is the whole line, which the compat rule
    // cannot see -- and a browser without one is told the name instead, which
    // is the thing somebody actually needs.
    // eslint-disable-next-line compat/compat
    if (!navigator.clipboard) {
      notification.warning(said);
      return;
    }
    // eslint-disable-next-line compat/compat
    navigator.clipboard
      .writeText(cell.name)
      .then(() => notification.success(`Copied. ${said}`))
      .catch(() => notification.warning(said));
  }, [cell.name]);

  if (editing && canEdit) {
    return (
      <input
        className="notebook-cell-handle-input"
        value={draft}
        autoFocus
        onChange={(e) => setDraft(e.target.value)}
        onBlur={() => {
          onEditing(false);
          const wanted = draft.trim();
          if (!abandoned.current && wanted && wanted !== cell.name) {
            // The server owns the rules -- letters, digits and underscores,
            // not starting with a digit, unique in the notebook -- and it
            // answers with the sentence saying which one was broken. Checking
            // here as well would be a second copy of them.
            onRename(wanted).catch((reason) =>
              notification.error((reason && reason.message) || "That name will not do.")
            );
          }
          abandoned.current = false;
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.target.blur();
          }
          if (e.key === "Escape") {
            abandoned.current = true;
            setDraft(cell.name);
            e.target.blur();
          }
        }}
        data-test="CellHandleInput"
        aria-label="What cells below call this one"
      />
    );
  }

  return (
    <Tooltip title={`Cells below this one read it as ${cell.name}. Click to copy.`}>
      <PlainButton className="notebook-cell-handle" onClick={copy} data-test="CellHandle">
        {cell.name}
      </PlainButton>
    </Tooltip>
  );
}

CellHandle.propTypes = {
  cell: PropTypes.object.isRequired,
  canEdit: PropTypes.bool,
  editing: PropTypes.bool,
  onEditing: PropTypes.func,
  onRename: PropTypes.func,
};

CellHandle.defaultProps = {
  canEdit: false,
  editing: false,
  onEditing: () => {},
  onRename: () => Promise.resolve(),
};

/*
  The names this cell can read, under the box it would type them in.

  Autocomplete only helps somebody who already knows there is something to
  complete. This line is the other half: an empty cell says what is there to
  read before a key is pressed, and a cell with code says it where the eye
  already is. Only what is *really* readable -- a name is here because a cell
  above handed a table over, so a cell that printed is correctly absent and
  nobody writes a reference that cannot resolve.

  "Available to read", not "reads": it lists what this cell *may* use, and a
  cell may use any of them or none. Worded the other way it was a claim about
  somebody's code, which is both wrong and not the page's business.
*/
export function AvailableToRead({ available, canEdit }) {
  if (!canEdit || !size(available)) {
    return null;
  }
  return (
    <div className="notebook-cell-available" data-test="AvailableToRead">
      Available to read{" "}
      {map(available, (one, nth) => (
        <React.Fragment key={one.name}>
          {nth > 0 && ", "}
          <Tooltip
            title={
              size(one.columns) ? `${one.name}: ${map(one.columns, (column) => column.name).join(", ")}` : one.name
            }
          >
            <code>{one.name}</code>
          </Tooltip>
        </React.Fragment>
      ))}
    </div>
  );
}

AvailableToRead.propTypes = {
  available: PropTypes.arrayOf(PropTypes.object),
  canEdit: PropTypes.bool,
};

AvailableToRead.defaultProps = { available: [], canEdit: false };

/*
  One line standing in for a folded cell, so folding does not make it
  invisible -- somebody scanning a notebook should be able to tell what they
  have hidden without unfolding each one to find out.
*/
export function summarise(cell, produced) {
  if (!cell.last_run_at) {
    return "Not run yet.";
  }
  if (produced === "text") {
    return "Produced text.";
  }
  if (produced === "figure") {
    return "Produced a chart.";
  }
  if (produced === "table") {
    return "Produced a table.";
  }
  return "Has run.";
}

/*
  What a cell produced.

  A table when it produced one, and the printout when it did not -- which is
  also the line that tells somebody a later cell cannot read this. The rows
  shown are the truncated slice the server stored for display; the whole result
  is in the notebook's own store, which is what the next cell reads.
*/
export function CellOutput({
  cell,
  produced,
  result,
  onRemoveChart,
  onAddVisualization,
  onResizeChart,
  onResizeTable,
  onResizeFigure,
}) {
  // Read up here because the figure branch returns before the chart's own
  // declarations are reached.
  const figureHeight = (cell.options || {}).figureHeight || 420;
  // `result` is the endpoint's answer -- `{id, data, row_count, handed_on}` --
  // so the rows are one level in. Reading it as the rows themselves drew an
  // empty table and an empty printout, which is what the test caught.
  const data = (result && result.data) || null;
  const handedOn = result && result.handed_on;
  // How long it took, beside how much came back: the two questions somebody
  // asks of a result before reading a single row of it.
  const runtime = result && result.runtime;
  // What the cell printed on the way to its table. A cell that prints what it
  // is doing and then shows a dataframe gets both, rather than having to pick
  // -- for `produced === "text"` the printing *is* the output, so it is not
  // shown twice.
  const printed = produced === "text" ? null : (result && result.printed) || null;
  if (!data) {
    return (
      <div className="notebook-cell-output notebook-cell-output-empty" data-test="CellOutput">
        {produced === "text" ? "This cell produced text." : "This cell has run. Its output is not loaded here."}
      </div>
    );
  }
  if (produced === "figure") {
    // The spec is stored as JSON in a single cell, the same way text is --
    // one place a cell's output lives, whatever shape it has.
    let picture = null;
    try {
      const held = data.rows && data.rows[0] && data.rows[0].figure;
      picture = typeof held === "string" ? JSON.parse(held) : held;
    } catch (e) {
      picture = null;
    }
    return (
      <div className="notebook-cell-output" data-test="CellOutput">
        {printed && (
          <pre className="notebook-cell-printed" data-test="CellPrinted">
            {printed}
          </pre>
        )}
        {/*
          A picture gets the same handle as a chart. It is the output a
          Python cell most often ends on -- a Plotly figure, a matplotlib
          PNG -- and it was the one output with no say in its own height.
        */}
        <ResizablePane
          height={figureHeight}
          onResize={onResizeFigure}
          label="Drag to resize this picture"
          test="CellFigurePane"
        >
          <CellFigure figure={picture} />
        </ResizablePane>
      </div>
    );
  }
  if (produced === "text") {
    const printed = map(data.rows, (row) => row.output).join("\n");
    return (
      <pre className="notebook-cell-output notebook-cell-output-text" data-test="CellOutput">
        {printed}
      </pre>
    );
  }
  const columns = map(data.columns, (column) => ({
    title: column.name,
    dataIndex: column.name,
    key: column.name,
    render: (value) =>
      value === null || value === undefined ? <span className="notebook-cell-null">null</span> : String(value),
  }));
  const printout = printed ? (
    <pre className="notebook-cell-printed" data-test="CellPrinted">
      {printed}
    </pre>
  ) : null;
  /*
    The table and the chart as tabs, the way a query's results are.

    A chart used to *replace* the table, with a "Show the table instead"
    link to get back -- which made the chart feel like a mode rather than a
    view of the same rows. Tabs say what it is: one result, looked at two
    ways, and switching costs nothing because both draw the rows already on
    the page.

    "Add a visualization" is offered only where one can be made: a cell that
    printed, or produced a picture, has no relation to chart.
  */
  const chart = (cell.options || {}).visualization;
  const shown = size(data.rows);

  // The height of the scrolling body, which is the number the handle under
  // the table drags. Kept on the cell beside the chart's, so a result sized
  // to be readable stays that way for whoever opens the notebook next.
  const tableHeight = (cell.options || {}).tableHeight || 320;

  const table = (
    <>
      <Table
        size="small"
        columns={columns}
        dataSource={map(data.rows, (row, index) => ({ ...row, key: index }))}
        pagination={false}
        scroll={{ x: true, y: tableHeight }}
      />
      <TableResizeHandle height={tableHeight} onResize={onResizeTable} />
      {/*
        What this is a slice *of*. The whole result is in the notebook's own
        store and is what the next cell reads -- so saying "1,000 rows" here
        when there were four million would be the page implying the handoff is
        as small as the view.
      */}
      <div className="notebook-cell-output-count" data-test="CellRowCount">
        {handedOn > shown
          ? `first ${shown.toLocaleString()} of ${handedOn.toLocaleString()} rows — the whole result is what the next cell reads`
          : `${(handedOn === null || handedOn === undefined ? shown : handedOn).toLocaleString()} ${
              (handedOn === null || handedOn === undefined ? shown : handedOn) === 1 ? "row" : "rows"
            }`}
        {runtime !== null && runtime !== undefined && ` · ${runtime < 1 ? runtime.toFixed(2) : runtime.toFixed(1)}s`}
      </div>
    </>
  );

  /*
    How tall a chart is drawn, dragged rather than chosen.

    Three sizes were a guess at what people want; what they actually want is
    this one, this tall. Kept on the cell like the other view settings, so
    somebody who sized a chart to be readable sized it for whoever opens the
    notebook next.
  */
  const chartHeight = (cell.options || {}).chartHeight || 420;

  const addVisualization = onAddVisualization ? (
    <Button type="link" size="small" onClick={onAddVisualization} data-test="AddVisualization">
      <PlusOutlinedIcon /> {chart ? "Edit the chart" : "Add a visualization"}
    </Button>
  ) : null;

  return (
    <div className="notebook-cell-output" data-test="CellOutput">
      {printout}
      <Tabs
        type="card"
        size="small"
        className="notebook-cell-tabs"
        defaultActiveKey={chart ? "chart" : "table"}
        tabBarExtraContent={addVisualization}
        animated={false}
        data-test="CellOutputTabs"
      >
        <Tabs.TabPane tab="Table" key="table">
          {table}
        </Tabs.TabPane>
        {chart && (
          <Tabs.TabPane
            tab={
              <span data-test="CellChartTab">
                {chart.name}
                {onRemoveChart && (
                  <CloseOutlinedIcon
                    className="notebook-cell-tab-remove"
                    onClick={(e) => {
                      e.stopPropagation();
                      onRemoveChart();
                    }}
                    data-test="RemoveChart"
                    aria-label="Remove this chart"
                  />
                )}
              </span>
            }
            key="chart"
          >
            <ResizablePane
              height={chartHeight}
              onResize={onResizeChart}
              label="Drag to resize this chart"
              test="CellChart"
            >
              <Renderer type={chart.type} data={data} options={chart.options} visualizationName={chart.name} />
            </ResizablePane>
          </Tabs.TabPane>
        )}
      </Tabs>
    </div>
  );
}

/*
  How long this cell has been running.

  A cell that takes a while used to look exactly like a cell that had
  finished: the Run button became a Stop button and nothing else moved, so
  the only way to tell a slow query from a finished one was to notice which
  icon was showing. A number that goes up says "still going" without anybody
  having to read the toolbar.

  Tenths below ten seconds, because that is the range where a person is
  deciding whether to wait; whole seconds after, because a flickering tenths
  digit for two minutes is noise. The clock ticks four times a second rather
  than on a rounder number -- a timer on a one-second period visibly stutters
  against the second it is displaying.
*/
export function elapsedLabel(ms) {
  const seconds = Math.max(0, ms) / 1000;
  if (seconds < 10) {
    return `${seconds.toFixed(1)}s`;
  }
  if (seconds < 60) {
    return `${Math.floor(seconds)}s`;
  }
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${String(Math.floor(seconds - minutes * 60)).padStart(2, "0")}s`;
}

export function RunningFor({ since }) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!since) {
      return;
    }
    setNow(Date.now());
    const tick = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(tick);
  }, [since]);

  return (
    <span className="notebook-cell-running" data-test="CellRunning" role="status" aria-live="polite">
      <LoadingOutlinedIcon />
      {/*
        Without a start time -- a cell somebody else set running, which
        arrives as notebook state rather than as a run this browser began --
        the spinner still says "going", and that is all that can honestly be
        said.
      */}
      {since ? <span className="notebook-cell-running-for">{elapsedLabel(now - since)}</span> : null}
    </span>
  );
}

RunningFor.propTypes = { since: PropTypes.number };
RunningFor.defaultProps = { since: null };

/*
  Dragging a height, shared by everything a cell can output.

  The handle is a strip across the bottom, the way a dashboard widget is
  resized -- grabbing an edge is the gesture people already know here. The
  height is written to the cell once, on release, rather than on every mouse
  move: a save per pixel would be a hundred requests for one drag.

  Listeners go on `window`, not the handle: a drag that outruns the pointer
  -- which every drag does -- leaves the element behind, and a handler bound
  to the handle stops getting moves the moment it does.
*/
export function useDragHeight(height, onResize, min) {
  const [dragging, setDragging] = useState(null);

  const start = useCallback(
    (e) => {
      if (!onResize) {
        return;
      }
      e.preventDefault();
      const from = e.clientY;
      const was = height;
      let latest = was;

      const move = (moved) => {
        // A floor, because something dragged to nothing cannot be dragged
        // back: the handle would have no room to sit in.
        latest = Math.max(min, Math.round(was + (moved.clientY - from)));
        setDragging(latest);
      };
      const done = () => {
        window.removeEventListener("mousemove", move);
        window.removeEventListener("mouseup", done);
        setDragging(null);
        if (latest !== was) {
          onResize(latest);
        }
      };
      window.addEventListener("mousemove", move);
      window.addEventListener("mouseup", done);
    },
    [height, onResize, min]
  );

  return { shown: dragging === null ? height : dragging, dragging, start };
}

function DragStrip({ dragging, onMouseDown, label, test }) {
  return (
    <div
      className={cx("notebook-cell-pane-handle", { "is-dragging": dragging !== null })}
      onMouseDown={onMouseDown}
      role="separator"
      aria-label={label}
      aria-orientation="horizontal"
      data-test={test}
    />
  );
}

DragStrip.propTypes = {
  dragging: PropTypes.number,
  onMouseDown: PropTypes.func.isRequired,
  label: PropTypes.string.isRequired,
  test: PropTypes.string.isRequired,
};

DragStrip.defaultProps = { dragging: null };

/*
  Anything you drag to the height you want: a chart, and a picture a Python
  cell ended on. Both are drawn into whatever room they are given, so the
  pane owns the height and the content fills it.
*/
export function ResizablePane({ height, onResize, min, label, test, children }) {
  const { shown, dragging, start } = useDragHeight(height, onResize, min);

  return (
    <div className="notebook-cell-pane" style={{ height: shown }} data-test={test}>
      <div className="notebook-cell-pane-body">{children}</div>
      {onResize && <DragStrip dragging={dragging} onMouseDown={start} label={label} test={`${test}Handle`} />}
    </div>
  );
}

ResizablePane.propTypes = {
  height: PropTypes.number,
  onResize: PropTypes.func,
  min: PropTypes.number,
  label: PropTypes.string,
  test: PropTypes.string,
  children: PropTypes.node,
};

ResizablePane.defaultProps = {
  height: 420,
  onResize: null,
  min: 160,
  label: "Drag to resize",
  test: "CellPane",
};

/*
  A table is not wrapped the way a chart is.

  antd scrolls the *body* at `scroll.y` while the header stays put, so the
  number being dragged is the body's height, not the table's. Wrapping the
  whole thing in a fixed-height box would fight that: the header, the
  horizontal scrollbar and the row count underneath would all have to be
  subtracted from the height by hand, and they are not all the same size on
  every install. The strip sits under the table and drags `scroll.y`
  directly, which is the number that actually decides how much you see.
*/
export function TableResizeHandle({ height, onResize, min }) {
  const { dragging, start } = useDragHeight(height, onResize, min);

  if (!onResize) {
    return null;
  }
  return (
    <div className="notebook-cell-table-handle">
      <DragStrip dragging={dragging} onMouseDown={start} label="Drag to resize this table" test="TableResizeHandle" />
    </div>
  );
}

TableResizeHandle.propTypes = {
  height: PropTypes.number,
  onResize: PropTypes.func,
  min: PropTypes.number,
};

TableResizeHandle.defaultProps = { height: 320, onResize: null, min: 120 };

CellOutput.propTypes = {
  cell: PropTypes.object.isRequired,
  produced: PropTypes.string,
  result: PropTypes.object,
  onRemoveChart: PropTypes.func,
  onAddVisualization: PropTypes.func,
  onResizeChart: PropTypes.func,
  onResizeTable: PropTypes.func,
  onResizeFigure: PropTypes.func,
};

CellOutput.defaultProps = {
  produced: null,
  result: null,
  onRemoveChart: null,
  onAddVisualization: null,
  onResizeChart: null,
  onResizeTable: null,
  onResizeFigure: null,
};
