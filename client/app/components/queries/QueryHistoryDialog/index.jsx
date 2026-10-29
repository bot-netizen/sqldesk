import { extend, isEqual } from "lodash";
import React, { useCallback, useEffect, useMemo, useState } from "react";
import PropTypes from "prop-types";
import Alert from "antd/lib/alert";
import Button from "antd/lib/button";
import Modal from "antd/lib/modal";
import Radio from "antd/lib/radio";
import Spin from "antd/lib/spin";
import Tag from "antd/lib/tag";

import { wrap as wrapDialog, DialogPropType } from "@/components/DialogWrapper";
import TimeAgo from "@/components/TimeAgo";
import { axios } from "@/services/axios";
import notification from "@/services/notification";
import diffLines, { unchanged } from "./diffLines";

import "./index.less";

/*
  What a query said before, and putting it back.

  Two questions, and they are not the same one, so the dialog asks which:
  **what changed here**, which is what a history is for, and **what restoring
  this would do**, which is the question somebody about to press the button
  actually has. A single diff would have answered one of them and quietly
  misled about the other.

  Restoring writes a new version rather than rewriting one. The list is
  therefore never shortened by using it, and the version somebody restored
  stays where it was -- which is what makes it safe to press.
*/

const RESTORES = ["name", "description", "query", "options", "schedule", "tags"];

function describe(value) {
  if (value === null || value === undefined || value === "") {
    return "nothing";
  }
  if (Array.isArray(value)) {
    return value.length ? value.join(", ") : "nothing";
  }
  if (typeof value === "object") {
    return "changed";
  }
  return String(value);
}

function Field({ label, from, to }) {
  return (
    <div className="query-history-field">
      <span className="query-history-field-name">{label}</span>
      <span className="query-history-field-from">{describe(from)}</span>
      <i className="fa fa-long-arrow-right m-l-5 m-r-5" aria-hidden="true" />
      <span className="query-history-field-to">{describe(to)}</span>
    </div>
  );
}

const OTHER_FIELDS = [
  ["name", "Name"],
  ["description", "Description"],
  ["tags", "Tags"],
  ["schedule", "Schedule"],
  ["options", "Options"],
];

function Diff({ diff }) {
  if (unchanged(diff)) {
    return <p className="query-history-same">The SQL is the same.</p>;
  }
  return (
    <pre className="query-history-diff" data-test="QueryHistoryDiff">
      {diff.map((line, index) => (
        <div key={index} className={`query-history-line query-history-${line.type}`}>
          <span className="query-history-gutter">
            {line.type === "added" ? "+" : line.type === "removed" ? "−" : " "}
          </span>
          {line.text || " "}
        </div>
      ))}
    </pre>
  );
}

function QueryHistoryDialog({ dialog, query, canRestore, unsaved }) {
  const [versions, setVersions] = useState(null);
  const [failed, setFailed] = useState(false);
  const [chosen, setChosen] = useState(0);
  const [against, setAgainst] = useState("previous");
  const [restoring, setRestoring] = useState(false);

  useEffect(() => {
    axios
      .get(`api/queries/${query.id}/versions`)
      .then((data) => setVersions(data.versions))
      .catch(() => setFailed(true));
  }, [query.id]);

  const version = versions && versions[chosen];
  // "Against the current query" compares with the query as it is now, which is
  // not necessarily the newest version: an unsaved edit is in neither.
  const base = useMemo(() => {
    if (!versions || !version) {
      return null;
    }
    if (against === "current") {
      return pickFrom(query);
    }
    const older = versions[chosen + 1];
    return older ? older.values : {};
  }, [against, chosen, versions, version, query]);

  const diff = useMemo(() => (version && base ? diffLines(base.query, version.values.query) : []), [base, version]);

  const restore = useCallback(() => {
    setRestoring(true);
    return axios
      .post(`api/queries/${query.id}/versions/${version.id}/restore`)
      .then((updated) => {
        notification.success(`Version ${version.number} restored, as a new version.`);
        dialog.close(extend(query.clone(), updated));
      })
      .catch(() => {
        setRestoring(false);
        notification.error("Could not restore that version.");
      });
  }, [dialog, query, version]);

  // Restoring replaces what is in the editor. With unsaved changes there it
  // used to discard them without a word, and the guard against leaving with
  // unsaved changes never fired, because the restore reset what counts as
  // saved. Asked first now.
  const confirmRestore = useCallback(() => {
    if (!unsaved) {
      restore();
      return;
    }
    Modal.confirm({
      title: `Restore version ${version.number}?`,
      content: "The editor has changes you have not saved. Restoring replaces them.",
      okText: "Restore and discard my changes",
      cancelText: "Keep editing",
      onOk: restore,
    });
  }, [unsaved, restore, version]);

  return (
    <Modal
      {...dialog.props}
      width={900}
      title="History"
      footer={[
        <Button key="close" onClick={() => dialog.dismiss()}>
          Close
        </Button>,
        canRestore && version && (
          <Button key="restore" type="primary" loading={restoring} onClick={confirmRestore} data-test="RestoreVersion">
            Restore version {version.number}
          </Button>
        ),
      ].filter(Boolean)}
    >
      <div className="query-history" data-test="QueryHistory">
        {failed && <Alert type="warning" showIcon message="Could not load this query's history." />}
        {!versions && !failed && (
          <div className="query-history-loading">
            <Spin />
          </div>
        )}
        {versions && versions.length === 0 && (
          <p className="query-history-same">
            Nothing recorded yet. Versions are written when a query is created and whenever it is edited.
          </p>
        )}
        {versions && versions.length > 0 && (
          <div className="query-history-body">
            <ul className="query-history-list" data-test="QueryHistoryList">
              {versions.map((entry, index) => (
                <li key={entry.id}>
                  <button
                    type="button"
                    className={index === chosen ? "query-history-entry is-chosen" : "query-history-entry"}
                    onClick={() => setChosen(index)}
                  >
                    <span className="query-history-number">#{entry.number}</span>
                    <TimeAgo date={entry.at} />
                    <span className="query-history-who">{entry.by ? entry.by.name : "a deleted user"}</span>
                    <span className="query-history-changed">
                      {entry.changed.map((label) => (
                        <Tag key={label}>{label}</Tag>
                      ))}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
            <div className="query-history-detail">
              <Radio.Group
                size="small"
                value={against}
                onChange={(event) => setAgainst(event.target.value)}
                className="m-b-10"
              >
                <Radio.Button value="previous">What changed here</Radio.Button>
                <Radio.Button value="current">Against the query now</Radio.Button>
              </Radio.Group>
              {base &&
                OTHER_FIELDS.filter(([field]) => !isEqual(base[field], version.values[field])).map(([field, label]) => (
                  <Field key={field} label={label} from={base[field]} to={version.values[field]} />
                ))}
              <Diff diff={diff} />
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}

/** The current query, in the shape a recorded version has. */
function pickFrom(query) {
  const taken = {};
  RESTORES.forEach((field) => {
    taken[field] = field === "query" ? query.query : query[field];
  });
  return taken;
}

QueryHistoryDialog.propTypes = {
  dialog: DialogPropType.isRequired,
  query: PropTypes.object.isRequired,
  canRestore: PropTypes.bool,
  // Whether the editor holds changes that are not saved.
  unsaved: PropTypes.bool,
};

QueryHistoryDialog.defaultProps = { canRestore: false, unsaved: false };

// The unwrapped component, for tests: `wrapDialog` exists to be opened from a
// menu, and a test that went through it would be testing the wrapper.
export { QueryHistoryDialog as Unwrapped };

export default wrapDialog(QueryHistoryDialog);
