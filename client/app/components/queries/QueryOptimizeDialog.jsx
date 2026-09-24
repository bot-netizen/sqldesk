import React from "react";
import PropTypes from "prop-types";
import Modal from "antd/lib/modal";
import Alert from "antd/lib/alert";
import Tag from "antd/lib/tag";
import { wrap as wrapDialog, DialogPropType } from "@/components/DialogWrapper";

import "./QueryOptimizeDialog.less";

/*
  What the deterministic half of the optimizer found.

  No model was asked and nothing was executed: this is the query's own shape,
  parsed. That is worth saying on the dialog, because "AI looked at my SQL" and
  "a parser applied seven rules" are different promises and only one of them is
  being kept here.
*/

const SEVERITY = {
  critical: { colour: "red", label: "Critical" },
  warning: { colour: "orange", label: "Warning" },
  info: { colour: "blue", label: "Worth knowing" },
};

function QueryOptimizeDialog({ dialog, result }) {
  const { applicable, reason, findings, dialect } = result;

  return (
    <Modal
      {...dialog.props}
      title="Optimize"
      footer={null}
      width={620}
      wrapProps={{ "data-test": "QueryOptimizeDialog" }}
    >
      <div className="query-optimize">
        {!applicable && <Alert type="info" showIcon message="Nothing to report" description={reason} />}

        {applicable && findings.length === 0 && (
          <Alert
            type="success"
            showIcon
            message="No findings"
            description="None of the rules matched. They look at the query's shape, not at how big your tables are — that comes later."
          />
        )}

        {applicable &&
          findings.map((finding) => {
            const severity = SEVERITY[finding.severity] || SEVERITY.info;
            return (
              <div className="query-optimize-finding" key={finding.rule} data-test={`Finding.${finding.rule}`}>
                <div className="query-optimize-finding-head">
                  <Tag color={severity.colour}>{severity.label}</Tag>
                  <strong>{finding.title}</strong>
                </div>
                <p className="query-optimize-detail">{finding.detail}</p>
                {finding.suggestion && <p className="query-optimize-suggestion">{finding.suggestion}</p>}
              </div>
            );
          })}

        {applicable && (
          <p className="query-optimize-note">
            Parsed as <code>{dialect}</code>. Nothing was executed and no model was asked — these are rules about the
            query's shape.
          </p>
        )}
      </div>
    </Modal>
  );
}

QueryOptimizeDialog.propTypes = {
  dialog: DialogPropType.isRequired,
  result: PropTypes.object, // eslint-disable-line react/forbid-prop-types
};

QueryOptimizeDialog.defaultProps = {
  result: { applicable: false, reason: "Nothing to look at yet.", findings: [] },
};

export default wrapDialog(QueryOptimizeDialog);
