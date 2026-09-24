import { toString } from "lodash";
import cx from "classnames";
import toHtml from "@/lib/markdown";
import React, { useState, useEffect, useCallback } from "react";
import PropTypes from "prop-types";
import { useDebouncedCallback } from "use-debounce";
import Modal from "antd/lib/modal";
import Input from "antd/lib/input";
import Radio from "antd/lib/radio";
import Tooltip from "@/components/Tooltip";
import Divider from "antd/lib/divider";
import Link from "@/components/Link";
import HtmlContent from "@sqldesk/viz/lib/components/HtmlContent";
import { wrap as wrapDialog, DialogPropType } from "@/components/DialogWrapper";
import notification from "@/services/notification";

import "./TextboxDialog.less";

const ALIGNMENTS = ["left", "center", "right"];

function TextboxDialog({ dialog, isNew, ...props }) {
  const [text, setText] = useState(toString(props.text));
  const [textStyle, setTextStyle] = useState(props.textStyle === "plain" ? "plain" : "card");
  const [align, setAlign] = useState(ALIGNMENTS.includes(props.align) ? props.align : "left");
  const [preview, setPreview] = useState(null);

  useEffect(() => {
    setText(props.text);
    setPreview(toHtml(props.text));
  }, [props.text]);

  const [updatePreview] = useDebouncedCallback(() => {
    setPreview(toHtml(text));
  }, 200);

  const handleInputChange = useCallback(
    (event) => {
      setText(event.target.value);
      updatePreview();
    },
    [updatePreview]
  );

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
        <Input.TextArea
          className="resize-vertical"
          rows="5"
          value={text}
          aria-label="Textbox widget content"
          onChange={handleInputChange}
          autoFocus
          placeholder="This is where you write some text"
        />
        <small>
          Supports{" "}
          <Link target="_blank" rel="noopener noreferrer" href="https://www.markdownguide.org/cheat-sheet/">
            <Tooltip title="Markdown guide opens in new window">Markdown</Tooltip>
          </Link>{" "}
          — headings, lists, tables, code blocks — and HTML.
        </small>

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
        {text && (
          <React.Fragment>
            <Divider dashed />
            <strong className="preview-title">Preview:</strong>
            <HtmlContent
              className={cx("preview markdown", { "preview-plain": textStyle === "plain" })}
              style={{ textAlign: align }}
            >
              {preview}
            </HtmlContent>
          </React.Fragment>
        )}
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
