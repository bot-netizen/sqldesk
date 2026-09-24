import React, { useState, useMemo } from "react";
import PropTypes from "prop-types";
import cx from "classnames";
import Input from "antd/lib/input";
import Tabs from "antd/lib/tabs";
import HtmlContent from "@sqldesk/viz/lib/components/HtmlContent";
import Link from "@/components/Link";
import Tooltip from "@/components/Tooltip";
import toHtml from "@/lib/markdown";

import "./MarkdownEditor.less";

/*
  Markdown, with somewhere to see what it will look like.

  The text and the picture of it are the same size and in the same place, so
  switching between them changes nothing but the content -- a preview stacked
  underneath the box would push the box up the screen as you typed, which is
  the one thing you cannot have while typing.

  Whatever is passed as `previewClassName` and `previewStyle` is what the
  saved thing will carry, so the preview is not a likeness of the result --
  it is the result, drawn early.
*/

export const WRITE = "write";
export const PREVIEW = "preview";

const MARKDOWN_HELP = "https://www.markdownguide.org/cheat-sheet/";

export default function MarkdownEditor({
  value,
  onChange,
  rows,
  placeholder,
  ariaLabel,
  autoFocus,
  maxLength,
  previewClassName,
  previewStyle,
  className,
  id,
}) {
  const [tab, setTab] = useState(WRITE);

  // Only while the preview is showing. There is no reason to run the parser
  // on every keystroke for a tab nobody is looking at, and the text cannot
  // change while it is.
  const html = useMemo(() => (tab === PREVIEW ? toHtml(value || "") : null), [tab, value]);

  // The two tabs are the same height, so switching does not move the dialog's
  // buttons out from under the pointer.
  const bodyHeight = { minHeight: rows * 22 + 10 };

  return (
    <div className={cx("markdown-editor", className)} data-test="MarkdownEditor">
      <Tabs
        activeKey={tab}
        onChange={setTab}
        size="small"
        animated={false}
        tabBarExtraContent={
          <small className="markdown-editor-hint">
            <Link target="_blank" rel="noopener noreferrer" href={MARKDOWN_HELP}>
              <Tooltip title="Markdown guide opens in new window">Markdown</Tooltip>
            </Link>{" "}
            and HTML
          </small>
        }
      >
        {/*
          Kept mounted: switching to the preview and back should return the
          caret and the scroll position where they were, not to the top of a
          freshly built box.
        */}
        <Tabs.TabPane tab="Write" key={WRITE} forceRender>
          <Input.TextArea
            id={id}
            className="resize-vertical"
            style={bodyHeight}
            rows={rows}
            value={value}
            aria-label={ariaLabel}
            maxLength={maxLength}
            onChange={(event) => onChange(event.target.value)}
            autoFocus={autoFocus}
            placeholder={placeholder}
            data-test="MarkdownEditor.Write"
          />
        </Tabs.TabPane>
        <Tabs.TabPane tab="Preview" key={PREVIEW}>
          {value ? (
            <HtmlContent
              className={cx("markdown markdown-editor-preview", previewClassName)}
              style={{ ...bodyHeight, ...previewStyle }}
              data-test="MarkdownEditor.Preview"
            >
              {html}
            </HtmlContent>
          ) : (
            <div className="markdown-editor-empty" style={bodyHeight} data-test="MarkdownEditor.Preview">
              Nothing to preview yet.
            </div>
          )}
        </Tabs.TabPane>
      </Tabs>
    </div>
  );
}

MarkdownEditor.propTypes = {
  value: PropTypes.string,
  onChange: PropTypes.func.isRequired,
  rows: PropTypes.number,
  placeholder: PropTypes.string,
  ariaLabel: PropTypes.string,
  autoFocus: PropTypes.bool,
  maxLength: PropTypes.number,
  previewClassName: PropTypes.string,
  previewStyle: PropTypes.object, // eslint-disable-line react/forbid-prop-types
  className: PropTypes.string,
  id: PropTypes.string,
};

MarkdownEditor.defaultProps = {
  value: "",
  rows: 5,
  placeholder: "",
  ariaLabel: "Markdown content",
  autoFocus: false,
  maxLength: undefined,
  previewClassName: null,
  previewStyle: null,
  className: null,
  id: undefined,
};
