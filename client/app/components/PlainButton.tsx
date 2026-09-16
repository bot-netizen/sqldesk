import classNames from "classnames";
import React from "react";

import "./PlainButton.less";

export interface PlainButtonProps extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, "type"> {
  type?: "link" | "button";
}

// Ref-forwarding matters here: this button is routinely used as the child of
// antd's Tooltip and Dropdown, which attach a ref to position the overlay.
// Without it those fall back to findDOMNode and React logs a warning.
const PlainButton = React.forwardRef<HTMLButtonElement, PlainButtonProps>(function PlainButton(
  { className, type, ...rest },
  ref
) {
  return (
    <button
      ref={ref}
      className={classNames("plain-button", "clickable", { "plain-button-link": type === "link" }, className)}
      type="button"
      {...rest}
    />
  );
});

export default PlainButton;
