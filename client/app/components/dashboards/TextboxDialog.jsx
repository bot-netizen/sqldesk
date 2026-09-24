import { toString } from "lodash";
import React, { useState, useEffect, useCallback } from "react";
import PropTypes from "prop-types";
import Modal from "antd/lib/modal";
import Radio from "antd/lib/radio";
import MarkdownEditor from "@/components/MarkdownEditor";
import { wrap as wrapDialog, DialogPropType } from "@/components/DialogWrapper";
import notification from "@/services/notification";

import "./TextboxDialog.less";

const ALIGNMENTS = ["left", "center", "right"];

function TextboxDialog({ dialog, isNew, ...props }) {
  const [text, setText] = useState(toString(props.text));
  const [textStyle, setTextStyle] = useState(props.textStyle === "plain" ? "plain" : "card");
  const [align, setAlign] = useState(ALIGNMENTS.includes(props.align) ? props.align : "left");

  useEffect(() => {
    setText(props.text);
  }, [props.text]);

  const saveWidget = useCallback(() => {
    dialog.close({ text, textStyle, align }).catch(() => {
      notification.error(isNew ? "Widget could not be added" : "Widget could not be saved");
    });
  }, [dialog, isNew, text, textStyle, align]);

  const confirmDialogDismiss = useCallback(() => {
    const changed =
      text !== props.text ||
      textStyle !== (props.textStyle === "plain" ? "plain" : "card") ||
      align !== (ALIGNMENTS.includes(props.align) ? props.align : "left");
    if (changed) {
      Modal.confirm({
        title: "Quit editing?",
        content: "Changes you made so far will not be saved. Are you sure?",
        okText: "Yes, quit",
        okType: "danger",
        onOk: () => dialog.dismiss(),
        maskClosable: true,
        autoFocusButton: null,
        style: { top: 170 },
      });
    } else {
      dialog.dismiss();
    }
  }, [dialog, text, textStyle, align, props.text, props.textStyle, props.align]);

  return (
    <Modal
      {...dialog.props}
      title={isNew ? "Add Textbox" : "Edit Textbox"}
      onOk={saveWidget}
      onCancel={confirmDialogDismiss}
      okText={isNew ? "Add to Dashboard" : "Save"}
      width={500}
      wrapProps={{ "data-test": "TextboxDialog" }}
    >
      <div className="textbox-dialog">
        {/*
          The preview carries the style and alignment chosen below, so what it
          shows is the widget, not an impression of it.
        */}
        <MarkdownEditor
          value={text}
          onChange={setText}
          rows={7}
          autoFocus
          ariaLabel="Textbox widget content"
          placeholder="This is where you write some text"
          previewClassName={textStyle === "plain" ? "preview-plain" : null}
          previewStyle={{ textAlign: align }}
        />

        <div className="textbox-settings">
          <div className="textbox-setting">
            <span className="textbox-setting-label">Style</span>
            <Radio.Group
              size="small"
              value={textStyle}
              data-test="TextboxDialog.Style"
              onChange={(e) => setTextStyle(e.target.value)}
            >
              <Radio.Button value="card">Card</Radio.Button>
              <Radio.Button value="plain">Plain</Radio.Button>
            </Radio.Group>
            <span className="textbox-setting-help">
              {textStyle === "plain"
                ? "No tile around it, so a heading divides the page instead of sitting on it."
                : "A tile, like every other widget."}
            </span>
          </div>

          <div className="textbox-setting">
            <span className="textbox-setting-label">Align</span>
            <Radio.Group
              size="small"
              value={align}
              data-test="TextboxDialog.Align"
              onChange={(e) => setAlign(e.target.value)}
            >
              <Radio.Button value="left">Left</Radio.Button>
              <Radio.Button value="center">Centre</Radio.Button>
              <Radio.Button value="right">Right</Radio.Button>
            </Radio.Group>
          </div>
        </div>
      </div>
    </Modal>
  );
}

TextboxDialog.propTypes = {
  dialog: DialogPropType.isRequired,
  isNew: PropTypes.bool,
  text: PropTypes.string,
  textStyle: PropTypes.oneOf(["card", "plain"]),
  align: PropTypes.oneOf(ALIGNMENTS),
};

TextboxDialog.defaultProps = {
  isNew: false,
  text: "",
  textStyle: "card",
  align: "left",
};

export default wrapDialog(TextboxDialog);
