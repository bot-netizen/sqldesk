import React, { useEffect, useState } from "react";
import PropTypes from "prop-types";
import Alert from "antd/lib/alert";
import { map, sortBy } from "lodash";

import LoadingState from "@/components/items-list/components/LoadingState";
import { axios } from "@/services/axios";

import NotebookCell from "./NotebookCell";
import { NotebookContents, NotebookSize } from "./Notebook";
import "./notebook.less";

/*
  A shared notebook, as somebody without an account sees it.

  Read-only by construction rather than by hiding buttons: `canEdit` is
  false, so no cell offers Run, a chart editor or a data source picker --
  and there is nothing behind them to call anyway, because the public
  endpoint serves the stored slices and nothing else.

  Nothing is re-run for a reader. A public dashboard refreshes its queries
  for whoever opens it; this cannot, which makes it the safer of the two: no
  warehouse is touched and the interpreter is never reachable.
*/
export default function PublicNotebookPage({ token }) {
  const [notebook, setNotebook] = useState(null);
  const [failed, setFailed] = useState(null);

  useEffect(() => {
    let live = true;
    axios
      .get(`api/notebooks/public/${token}`)
      .then((found) => live && setNotebook(found))
      .catch(() => live && setFailed("This link no longer works, or never did."));
    return () => {
      live = false;
    };
  }, [token]);

  if (failed) {
    return <Alert type="warning" showIcon message={failed} className="notebook-load-error" />;
  }
  if (!notebook) {
    return <LoadingState className="" />;
  }

  const cells = sortBy(notebook.cells || [], "position");

  return (
    <div className="notebook-page" data-test="PublicNotebookPage">
      <div className="notebook-header">
        <div className="notebook-title">
          <h3 data-test="NotebookName">{notebook.name}</h3>
          {notebook.description && <p className="notebook-description">{notebook.description}</p>}
          <NotebookSize cells={cells} />
        </div>
      </div>

      <div className="notebook-body">
        <NotebookContents cells={cells} />
        <div className="notebook-cells">
          {map(cells, (cell) => (
            <div key={cell.id} id={`cell-${cell.id}`}>
              <NotebookCell
                cell={cell}
                notebookId={notebook.id}
                canEdit={false}
                onChanged={() => Promise.resolve()}
                onRemoved={() => {}}
                onRunningChanged={() => {}}
              />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

PublicNotebookPage.propTypes = {
  token: PropTypes.string.isRequired,
};
