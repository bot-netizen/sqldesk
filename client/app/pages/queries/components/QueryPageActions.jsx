import { isFunction, map, filter, fromPairs, noop } from "lodash";
import React, { useEffect } from "react";
import PropTypes from "prop-types";
import Button from "antd/lib/button";
import KeyboardShortcuts from "@/services/KeyboardShortcuts";
import { ButtonTooltip } from "@/components/queries/QueryEditor/QueryEditorControls";

import "./QueryPageActions.less";

// Save and Execute used to sit in the strip under the editor, among the
// parameter, format and autocomplete controls. Those are all about writing the
// SQL; these two are what you do with it, so they belong with the page's other
// actions.
//
// The shortcuts have to move with them. QueryEditorControls binds a button's
// shortcut from inside the component that renders it, so hiding the buttons
// there would take mod+s and mod+enter with them.
export default function QueryPageActions({ saveButtonProps, executeButtonProps }) {
  useEffect(() => {
    const buttons = filter([saveButtonProps, executeButtonProps], (b) => b && b.shortcut && isFunction(b.onClick));
    if (buttons.length > 0) {
      const shortcuts = fromPairs(map(buttons, (b) => [b.shortcut, b.disabled ? noop : b.onClick]));
      KeyboardShortcuts.bind(shortcuts);
      return () => {
        KeyboardShortcuts.unbind(shortcuts);
      };
    }
  }, [saveButtonProps, executeButtonProps]);

  return (
    <span className="query-page-actions">
      {saveButtonProps !== false && (
        <ButtonTooltip title={saveButtonProps.title} shortcut={saveButtonProps.shortcut}>
          <Button
            className="m-r-5"
            disabled={saveButtonProps.disabled}
            loading={saveButtonProps.loading}
            onClick={saveButtonProps.onClick}
            data-test="SaveButton"
          >
            {!saveButtonProps.loading && <span className="fa fa-floppy-o m-r-5" aria-hidden="true" />}
            {saveButtonProps.text}
          </Button>
        </ButtonTooltip>
      )}
      {executeButtonProps !== false && (
        <ButtonTooltip title={executeButtonProps.title} shortcut={executeButtonProps.shortcut}>
          <Button
            className="m-r-5"
            type="primary"
            disabled={executeButtonProps.disabled}
            onClick={executeButtonProps.onClick}
            data-test="ExecuteButton"
          >
            <span className="zmdi zmdi-play m-r-5" aria-hidden="true" />
            {executeButtonProps.text}
          </Button>
        </ButtonTooltip>
      )}
    </span>
  );
}

const ButtonPropsPropType = PropTypes.oneOfType([
  PropTypes.bool, // `false` to hide the button
  PropTypes.shape({
    title: PropTypes.node,
    disabled: PropTypes.bool,
    loading: PropTypes.bool,
    onClick: PropTypes.func,
    text: PropTypes.node,
    shortcut: PropTypes.string,
  }),
]);

QueryPageActions.propTypes = {
  saveButtonProps: ButtonPropsPropType,
  executeButtonProps: ButtonPropsPropType,
};

QueryPageActions.defaultProps = {
  saveButtonProps: false,
  executeButtonProps: false,
};
