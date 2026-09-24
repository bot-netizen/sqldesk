import React, { useState } from "react";
import PropTypes from "prop-types";
import cx from "classnames";
import toHtml from "@/lib/markdown";
import Menu from "antd/lib/menu";
import HtmlContent from "@sqldesk/viz/lib/components/HtmlContent";
import TextboxDialog from "@/components/dashboards/TextboxDialog";
import Widget from "./Widget";

/*
  A textbox is how a dashboard is divided into sections, and a section
  heading in a white card with fifty empty pixels under it reads as a widget
  that failed to load. So a textbox can turn its tile off -- "plain" -- and
  then it is just words on the page, which is what a heading between two rows
  of charts should be.
*/
function settingsOf(widget) {
  const options = widget.options || {};
  return {
    textStyle: options.textStyle === "plain" ? "plain" : "card",
    align: ["left", "center", "right"].includes(options.align) ? options.align : "left",
  };
}

function TextboxWidget(props) {
  const { widget, canEdit } = props;
  const [text, setText] = useState(widget.text);
  const [settings, setSettings] = useState(() => settingsOf(widget));

  const editTextBox = () => {
    TextboxDialog.showModal({
      text: widget.text,
      ...settingsOf(widget),
    }).onClose(({ text: newText, textStyle, align }) => {
      widget.text = newText;
      // Merged, not replaced: `options` also holds the widget's position and
      // its parameter mappings.
      widget.options = { ...widget.options, textStyle, align };
      setText(newText);
      setSettings({ textStyle, align });
      return widget.save();
    });
  };

  const TextboxMenuOptions = [
    <Menu.Item key="edit" onClick={editTextBox}>
      Edit
    </Menu.Item>,
  ];

  if (!widget.width) {
    return null;
  }

  return (
    <Widget
      {...props}
      menuOptions={canEdit ? TextboxMenuOptions : null}
      className={cx("widget-text", `widget-text-${settings.textStyle}`)}
    >
      <HtmlContent className="body-row-auto scrollbox t-body p-15 markdown" style={{ textAlign: settings.align }}>
        {toHtml(text || "")}
      </HtmlContent>
    </Widget>
  );
}

TextboxWidget.propTypes = {
  widget: PropTypes.object.isRequired, // eslint-disable-line react/forbid-prop-types
  canEdit: PropTypes.bool,
};

TextboxWidget.defaultProps = {
  canEdit: false,
};

export default TextboxWidget;
