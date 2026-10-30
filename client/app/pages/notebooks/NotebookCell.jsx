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

const KINDS = { sql: "SQL", python: "Python" };

export default function NotebookCell({
  cell,
  notebookId,
  dataSources,
  canEdit,
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
        <span className="notebook-cell-name" data-test="CellName">
          {cell.name}
        </span>
        <span className="notebook-cell-kind">{KINDS[cell.kind] || cell.kind}</span>
        {cell.kind === "sql" && canEdit && (
          /*
            Empty is a meaning, not a missing value: a SQL cell with no data
            source reads the cells above it. The placeholder says so, and the
            tooltip says it in full, because a dropdown that looks unset is
            the one place somebody would assume nothing had been decided.
          */
          <Tooltip title="A data source to query, or nothing — then this cell reads the cells above it.">
            <Select
              className="notebook-cell-source-select"
              size="small"
              placeholder="Earlier cells"
              value={cell.data_source_id || undefined}
              allowClear
              onChange={(value) => save({ data_source_id: value || null })}
              data-test="CellDataSource"
            >
              {map(dataSources, (source) => (
                <Select.Option key={source.id} value={source.id}>
                  {source.name}
                </Select.Option>
              ))}
            </Select>
          </Tooltip>
        )}
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

      {notice && <Alert className="notebook-cell-notice" type="info" showIcon message={notice} data-test="CannotRun" />}
      {missing.length > 0 && (
        <Alert
          className="notebook-cell-notice"
          type="error"
          showIcon
          message={`${missing.join(", ")} ${missing.length === 1 ? "no longer exists" : "no longer exist"}, so this cell cannot be reproduced.`}
          data-test="MissingInputs"
        />
      )}
      {stale.length > 0 && (
        <Alert
          className="notebook-cell-notice"
          type="warning"
          showIcon
          message={`${stale.join(", ")} ${stale.length === 1 ? "has" : "have"} run since this did, so what is below was computed from older data.`}
          data-test="Stale"
        />
      )}

      <QueryEditor
        className="notebook-cell-editor"
        syntax={cell.kind === "python" ? "python" : "sql"}
        value={source}
        onChange={setSource}
        onBlur={() => source !== cell.source && save({ source })}
        autocompleteEnabled={false}
        schema={[]}
      />

      {error && <Alert className="notebook-cell-notice" type="error" showIcon message={error} data-test="CellError" />}
      {cell.last_run_at && !error && (
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
  onChanged: PropTypes.func.isRequired,
  onRemoved: PropTypes.func.isRequired,
  running: PropTypes.oneOfType([PropTypes.number, PropTypes.string]),
  onRunningChanged: PropTypes.func.isRequired,
};

NotebookCell.defaultProps = {
  dataSources: [],
  canEdit: false,
  running: null,
};

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
