import React from "react";
import PropTypes from "prop-types";
import Alert from "antd/lib/alert";

/*
  A result that is not all of the result, said where the rows are.

  It used to be a tooltip on a small orange icon in the footer, worded for
  Databricks -- which is how a cut-short result reads as the whole answer.
  Now the rows that were kept, why the rest was not, and what to do about it,
  above the table and the charts made from it.
*/
export function truncationMessage(rowCount, truncation) {
  const rows = (rowCount || 0).toLocaleString();
  if (truncation && truncation.reason === "size") {
    return {
      title: `Showing the first ${rows} rows: the full result is larger than this SQLDesk keeps for one query (${truncation.limit_mb} MB).`,
      detail:
        "The rest was not fetched, and the query was stopped on the data source. Add a LIMIT, a filter or an " +
        "aggregate to get what you need, or download it from the data source directly. Charts and downloads " +
        "here use these rows only. An administrator can raise the limit with queryResults.maxMB in the Helm " +
        "chart (SQLDESK_QUERY_RESULT_MAX_MB), together with the workers' memory.",
    };
  }
  return {
    title: `Showing the first ${rows} rows: the data source returned no more than that.`,
    detail:
      "Charts and downloads here use these rows only. Add a LIMIT, a filter or an aggregate to get what you need.",
  };
}

export default function ResultTruncatedNotice({ rowCount, truncation }) {
  const { title, detail } = truncationMessage(rowCount, truncation);
  return (
    <Alert
      data-test="ResultTruncatedNotice"
      type="warning"
      showIcon
      message={title}
      description={detail}
      className="m-b-10"
    />
  );
}

ResultTruncatedNotice.propTypes = {
  rowCount: PropTypes.number,
  truncation: PropTypes.shape({ reason: PropTypes.string, limit_mb: PropTypes.number }),
};

ResultTruncatedNotice.defaultProps = { rowCount: 0, truncation: null };
