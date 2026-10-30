import React, { useCallback, useEffect, useMemo, useState } from "react";
import PropTypes from "prop-types";
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

import NotebookCell from "./NotebookCell";
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

  const publish = useCallback(() => {
    Notebook.save(notebookId, { is_draft: false }).then(setNotebook);
  }, [notebookId]);

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
          <h3 data-test="NotebookName">{notebook.name}</h3>
          {notebook.is_draft && <span className="notebook-draft">Draft</span>}
          {notebook.description && <p className="notebook-description">{notebook.description}</p>}
        </div>
        <span className="notebook-header-spacer" />
        <InterpreterState state={interpreterState} onDetach={detach} />
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
        <Link href="notebooks" className="notebook-back">
          All notebooks
        </Link>
      </div>

      {cells.length === 0 && (
        <Alert
          className="notebook-empty"
          type="info"
          showIcon
          message="A notebook starts with a SQL cell."
          description="A code cell cannot query — it reads what a SQL cell above it fetched. So the first cell is always SQL."
        />
      )}

      <div className="notebook-cells">
        {map(cells, (cell) => (
          <NotebookCell
            key={cell.id}
            cell={cell}
            notebookId={notebook.id}
            dataSources={dataSources}
            canEdit={notebook.can_edit}
            running={running}
            onRunningChanged={(busy) => setRunning(busy ? cell.id : null)}
            onChanged={onCellChanged}
            onRemoved={onCellRemoved}
          />
        ))}
      </div>
    </div>
  );
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
