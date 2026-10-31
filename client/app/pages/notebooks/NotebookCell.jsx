import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import PropTypes from "prop-types";
import cx from "classnames";
import Alert from "antd/lib/alert";
import Button from "antd/lib/button";
import Select from "antd/lib/select";
import Tooltip from "antd/lib/tooltip";
import Table from "antd/lib/table";
import { map, size } from "lodash";

import { getEditorComponents } from "@/components/queries/editor-components";
import Notebook from "@/services/notebook";
import CellVisualizationDialog from "./CellVisualizationDialog";
import CellFigure from "./CellFigure";
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
  onChanged,
  onRemoved,
  running,
  onRunningChanged,
}) {
  const [source, setSource] = useState(cell.source || "");
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
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
  const setOption = useCallback(
    (changes) => save({ options: { ...(cell.options || {}), ...changes } }),
    [cell, save]
  );

  const collapsed = !!(cell.options || {}).collapsed;
  const hideCode = !!(cell.options || {}).hideCode;
  const hideOutput = !!(cell.options || {}).hideOutput;

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
  const produced = (cell.options || {}).produced;

  return (
    <div className={cx("notebook-cell", `notebook-cell-${cell.kind}`)} data-test={`NotebookCell-${cell.name}`}>
      <div className="notebook-cell-header">
        <Tooltip title={collapsed ? "Show this cell" : "Fold this cell away"}>
          <Button
            size="small"
            type="text"
            className="notebook-cell-fold"
            onClick={() => setOption({ collapsed: !collapsed })}
            data-test="CollapseCell"
            aria-expanded={!collapsed}
            aria-label={collapsed ? "Show this cell" : "Fold this cell away"}
          >
            {collapsed ? "▸" : "▾"}
          </Button>
        </Tooltip>
        <CellTitle
          cell={cell}
          canEdit={canEdit}
          onChange={(title) => title !== (cell.title || "") && save({ title })}
        />
        <span className="notebook-cell-name" data-test="CellName">
          {cell.name}
        </span>

        <RunsOn
          cell={cell}
          dataSources={dataSources}
          canEdit={canEdit}
          cluster={cluster}
          onChange={save}
        />
        {size(cell.reads) > 0 && (
          <span className="notebook-cell-reads" data-test="CellReads">
            reads {cell.reads.join(", ")}
          </span>
        )}
        <span className="notebook-cell-spacer" />
        {busy || running === cell.id ? (
          <Button size="small" onClick={stop} data-test="StopCell">
            Stop
          </Button>
        ) : (
          <Tooltip title={notice}>
            <Button size="small" type="primary" onClick={run} disabled={!!blocked || !!running} data-test="RunCell">
              Run
            </Button>
          </Tooltip>
        )}
        {/*
          Code and output hide separately, which is the whole point: reading a
          finished notebook and writing one want opposite things on screen.
          Somebody presenting a result wants the SQL gone; somebody debugging
          wants the table gone and the query in front of them.
        */}
        {!collapsed && (
          <Button
            size="small"
            type="text"
            onClick={() => setOption({ hideCode: !hideCode })}
            data-test="ToggleCode"
            aria-pressed={!hideCode}
          >
            {hideCode ? "Show code" : "Hide code"}
          </Button>
        )}
        {!collapsed && cell.last_run_at && (
          <Button
            size="small"
            type="text"
            onClick={() => setOption({ hideOutput: !hideOutput })}
            data-test="ToggleOutput"
            aria-pressed={!hideOutput}
          >
            {hideOutput ? "Show output" : "Hide output"}
          </Button>
        )}
        {/*
          The whole result, for somebody moving data rather than looking at
          it. Only on a cell that produced a relation: there is nothing to
          take out of a cell that printed.
        */}
        {!collapsed && produced === "table" && cell.last_run_at && (
          <Tooltip title="Download every row — not the slice shown here.">
            <a
              className="notebook-cell-download"
              href={Notebook.downloadUrl(notebookId, cell.id)}
              download
              data-test="DownloadCell"
            >
              Download
            </a>
          </Tooltip>
        )}
        {canEdit && produced === "table" && result && (
          <Button size="small" type="text" onClick={visualize} data-test="VisualizeCell">
            {(cell.options || {}).visualization ? "Edit chart" : "Chart"}
          </Button>
        )}
        {canEdit && (
          <Button size="small" type="text" onClick={remove} data-test="RemoveCell">
            Remove
          </Button>
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
        <QueryEditor
          className="notebook-cell-editor"
          syntax={cell.kind === "python" ? "python" : "sql"}
          value={source}
          onChange={setSource}
          onBlur={() => source !== cell.source && save({ source })}
          autocompleteEnabled={false}
          schema={[]}
        />
      )}

      {!collapsed && error && (
        <Alert className="notebook-cell-notice" type="error" showIcon message={error} data-test="CellError" />
      )}
      {!collapsed && !hideOutput && cell.last_run_at && !error && (
        <CellOutput cell={cell} produced={produced} result={result} onRemoveChart={removeChart} />
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
  onChanged: PropTypes.func.isRequired,
  onRemoved: PropTypes.func.isRequired,
  running: PropTypes.oneOfType([PropTypes.number, PropTypes.string]),
  onRunningChanged: PropTypes.func.isRequired,
};

NotebookCell.defaultProps = {
  dataSources: [],
  canEdit: false,
  cluster: false,
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

  if (!canEdit) {
    return (
      <span className="notebook-cell-runs-on-static" data-test="RunsOn">
        {describeWhatItRunsOn(cell, dataSources, cluster)}
      </span>
    );
  }

  return (
    <span className="notebook-cell-runs-on" data-test="RunsOn">
      <Select size="small" value={value} onChange={change} className="notebook-cell-runs-on-select" dropdownMatchSelectWidth={false}>
        <Select.OptGroup label="Query a warehouse">
          {map(dataSources, (source) => (
            <Select.Option key={source.id} value={`${SOURCE_PREFIX}${source.id}`}>
              {source.name}
            </Select.Option>
          ))}
        </Select.OptGroup>
        <Select.OptGroup label="Stay in this notebook">
          <Select.Option value={EARLIER_CELLS}>SQL over earlier cells</Select.Option>
        </Select.OptGroup>
        <Select.OptGroup label="Run Python — no data source">
          <Select.Option value={PYTHON}>{cluster ? "Python, with the Spark cluster" : "Python"}</Select.Option>
        </Select.OptGroup>
      </Select>
      <span className="notebook-cell-runs-on-said" data-test="RunsOnSaid">
        {describeWhatItRunsOn(cell, dataSources, cluster)}
      </span>
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
  The same decision in words.

  The sentence the user asked for: if it runs Python, say outright that no
  data source is needed, rather than leaving an empty control to imply
  something is missing.
*/
export function describeWhatItRunsOn(cell, dataSources, cluster) {
  if (cell.kind === "python") {
    return cluster
      ? "Python, with `spark` — reads earlier cells; no data source"
      : "Python — reads earlier cells; no data source";
  }
  if (!cell.data_source_id) {
    return "SQL over earlier cells — no data source";
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

  The name stays visible beside it, because the name is what later cells are
  written against -- somebody who titles a cell "Orders, cleaned" still needs
  to know they type `orders` to read it.
*/
export function CellTitle({ cell, canEdit, onChange }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(cell.title || "");

  useEffect(() => setDraft(cell.title || ""), [cell.id, cell.title]);

  const commit = useCallback(() => {
    setEditing(false);
    onChange(draft.trim());
  }, [draft, onChange]);

  if (!canEdit) {
    return cell.title ? (
      <span className="notebook-cell-title" data-test="CellTitle">
        {cell.title}
      </span>
    ) : null;
  }

  if (editing) {
    return (
      <input
        className="notebook-cell-title-input"
        value={draft}
        autoFocus
        placeholder="Name this step"
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            commit();
          }
          if (e.key === "Escape") {
            setDraft(cell.title || "");
            setEditing(false);
          }
        }}
        data-test="CellTitleInput"
      />
    );
  }

  return (
    <span
      className={cx("notebook-cell-title", { "notebook-cell-title-unset": !cell.title })}
      onClick={() => setEditing(true)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && setEditing(true)}
      data-test="CellTitle"
    >
      {cell.title || "Name this step"}
    </span>
  );
}

CellTitle.propTypes = {
  cell: PropTypes.object.isRequired,
  canEdit: PropTypes.bool,
  onChange: PropTypes.func.isRequired,
};

CellTitle.defaultProps = { canEdit: false };

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
export function CellOutput({ cell, produced, result, onRemoveChart }) {
  // `result` is the endpoint's answer -- `{id, data, row_count, handed_on}` --
  // so the rows are one level in. Reading it as the rows themselves drew an
  // empty table and an empty printout, which is what the test caught.
  const data = (result && result.data) || null;
  const handedOn = result && result.handed_on;
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
        <CellFigure figure={picture} />
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
  const chart = (cell.options || {}).visualization;
  if (chart) {
    return (
      <div className="notebook-cell-output notebook-cell-output-chart" data-test="CellOutput">
        {printout}
        <div className="notebook-cell-chart-header">
          <span className="notebook-cell-chart-name">{chart.name}</span>
          {onRemoveChart && (
            <Button size="small" type="text" onClick={onRemoveChart} data-test="RemoveChart">
              Show the table instead
            </Button>
          )}
        </div>
        <Renderer type={chart.type} data={data} options={chart.options} visualizationName={chart.name} />
      </div>
    );
  }

  const shown = size(data.rows);
  return (
    <div className="notebook-cell-output" data-test="CellOutput">
      {printout}
      <Table
        size="small"
        columns={columns}
        dataSource={map(data.rows, (row, index) => ({ ...row, key: index }))}
        pagination={false}
        scroll={{ x: true, y: 320 }}
      />
      {/*
        What this is a slice *of*. The whole result is in the notebook's own
        store and is what the next cell reads -- so saying "1,000 rows" here
        when there were four million would be the page implying the handoff is
        as small as the view.
      */}
      {handedOn > shown && (
        <div className="notebook-cell-output-count" data-test="CellRowCount">
          {`first ${shown.toLocaleString()} of ${handedOn.toLocaleString()} rows — the whole result is what the next cell reads`}
        </div>
      )}
    </div>
  );
}

CellOutput.propTypes = {
  cell: PropTypes.object.isRequired,
  produced: PropTypes.string,
  result: PropTypes.object,
  onRemoveChart: PropTypes.func,
};

CellOutput.defaultProps = { produced: null, result: null, onRemoveChart: null };
