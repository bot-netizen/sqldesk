import React, { useEffect, useState } from "react";
import PropTypes from "prop-types";
import Alert from "antd/lib/alert";
import Button from "antd/lib/button";

import { axios } from "@/services/axios";
import { currentUser } from "@/services/auth";
import useDuplicateDashboard from "../hooks/useDuplicateDashboard";

/*
  Whether this dashboard can be sent, said as the dialog opens.

  A dashboard is sent -- to Slack, now or on a schedule, or by email -- as a
  one-page picture: up to twelve widgets, one page tall. That used to be the
  reply to pressing Send, after somebody had picked a channel and typed a
  message. Now the dialog asks first, and when the answer is no it says what
  to change: how many widgets to remove, or that it is too tall -- and offers
  a copy of the dashboard to trim, for the common case of a big dashboard
  somebody wants a few charts of every morning.
*/

export function useSendable(dashboard) {
  const [check, setCheck] = useState(null);

  useEffect(() => {
    let cancelled = false;
    axios
      .get(`api/dashboards/${dashboard.id}/sendable`)
      .then((answer) => {
        if (!cancelled) setCheck(answer);
      })
      .catch(() => {
        // Not knowing is not the same as "too big": the server checks again
        // when somebody presses Send, and says so then.
        if (!cancelled) setCheck(null);
      });
    return () => {
      cancelled = true;
    };
  }, [dashboard.id]);

  return check;
}

export default function SendableNotice({ dashboard, check }) {
  const [isDuplicating, duplicate] = useDuplicateDashboard(dashboard);

  if (!check || check.fits) {
    return null;
  }

  return (
    <Alert
      className="m-b-15"
      type="warning"
      showIcon
      data-test="SendableNotice"
      message={check.problem}
      description={
        <>
          <div>{check.advice}</div>
          {currentUser.hasPermission("edit_dashboard") && (
            <Button size="small" className="m-t-10" loading={isDuplicating} onClick={duplicate}>
              Make a copy to trim <i className="fa fa-external-link m-l-5" aria-hidden="true" />
              <span className="sr-only">(opens in a new tab)</span>
            </Button>
          )}
        </>
      }
    />
  );
}

SendableNotice.propTypes = {
  dashboard: PropTypes.shape({ id: PropTypes.number }).isRequired,
  check: PropTypes.shape({
    fits: PropTypes.bool,
    problem: PropTypes.string,
    advice: PropTypes.string,
  }),
};

SendableNotice.defaultProps = {
  check: null,
};
