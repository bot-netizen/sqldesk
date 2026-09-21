import React, { useMemo, useState, useEffect } from "react";
import moment from "moment";
import PropTypes from "prop-types";
import { Moment } from "@/components/proptypes";

export default function Timer({ from }) {
  // NaN when there is nothing to count from, which is the normal state: the
  // dashboard's refresh indicator is in the DOM of every widget all the time
  // and only becomes visible while that widget refreshes.
  const startTime = useMemo(() => moment(from).valueOf(), [from]);
  const running = Number.isFinite(startTime);
  const [value, setValue] = useState(null);

  useEffect(() => {
    // Without this a widget that is not refreshing still woke up once a second
    // to subtract from NaN and render "Invalid date" into a hidden element --
    // once per widget, for as long as the page is open. A dashboard left on a
    // wall never closes.
    if (!running) {
      setValue(null);
      return undefined;
    }

    function update() {
      const diff = moment.now() - startTime;
      const format = diff > 1000 * 60 * 60 ? "HH:mm:ss" : "mm:ss"; // no HH under an hour
      setValue(moment.utc(diff).format(format));
    }
    update();

    const timer = setInterval(update, 1000);
    return () => clearInterval(timer);
  }, [startTime, running]);

  return <span className="rd-timer">{value}</span>;
}

Timer.propTypes = {
  from: PropTypes.oneOfType([PropTypes.string, PropTypes.number, PropTypes.instanceOf(Date), Moment]),
};

Timer.defaultProps = {
  from: null,
};
