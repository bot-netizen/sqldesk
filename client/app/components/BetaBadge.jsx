import React from "react";
import PropTypes from "prop-types";
import cx from "classnames";
import Tooltip from "antd/lib/tooltip";
import { featureIsBeta } from "@/services/auth";

import "./BetaBadge.less";

/*
  A feature that is shipped and still settling.

  Which features those are is decided in `sqldesk/features.py` and arrives on
  `grantableFeatures`, so this asks rather than carrying its own list: a
  feature that leaves beta stops being badged everywhere the moment the flag
  moves, and nobody has to remember which pages draw it.

  It says what beta means, because the word on its own means four different
  things depending on who is reading it. Here it means: use it, it works, and
  what it does may change between releases in ways the rest of the app will
  not.
*/
export default function BetaBadge({ feature, className, say }) {
  if (!featureIsBeta(feature)) {
    return null;
  }
  return (
    <Tooltip title={say}>
      <span className={cx("beta-badge", className)} data-test="BetaBadge">
        Beta
      </span>
    </Tooltip>
  );
}

BetaBadge.propTypes = {
  feature: PropTypes.string.isRequired,
  className: PropTypes.string,
  say: PropTypes.string,
};

BetaBadge.defaultProps = {
  className: null,
  say: "Shipped and supported, and still settling: what it does may change between releases.",
};
