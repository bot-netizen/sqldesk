import React from "react";
import PropTypes from "prop-types";

import logoUrl from "@/assets/images/sqldesk_icon.svg";

import "./ScreenshotFrame.less";

/*
  The branded page a picture is taken on.

  Export as image draws a dashboard onto a page with the SQLDesk mark, the
  dashboard's name and when it was made (dashboards/export/compose.js). The
  pictures the server takes -- Send to Slack, a subscription, an alert's
  attachment -- were the bare page, edge to edge: the same dashboard,
  arriving in a channel looking flat and anonymous beside the one somebody
  exported by hand.

  This is that page, in HTML rather than on a canvas, for the renderer to
  photograph: the same margin, the same 64px band, the mark, the name, and
  the provenance on the right. The measurements match compose.js so the two
  kinds of picture are the same artefact; a change to one belongs in both.
*/

/** When the picture was taken, unambiguously: a channel spans time zones. */
export function generatedAt(date = new Date()) {
  try {
    return new Intl.DateTimeFormat("en-GB", {
      day: "numeric",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      timeZoneName: "short",
    }).format(date);
  } catch (error) {
    return date.toISOString().slice(0, 16).replace("T", " ") + " UTC";
  }
}

export default function ScreenshotFrame({ title, fields, children }) {
  const shown = fields.filter((field) => field && field.value);
  return (
    <div className="screenshot-frame" data-test="ScreenshotFrame">
      <header className="screenshot-frame__header">
        <img className="screenshot-frame__logo" src={logoUrl} alt="" />
        <span className="screenshot-frame__brand">SQLDesk</span>
        {title && (
          <>
            <span className="screenshot-frame__divider" aria-hidden="true" />
            <span className="screenshot-frame__title" title={title}>
              {title}
            </span>
          </>
        )}
        {shown.length > 0 && (
          <span className="screenshot-frame__fields">
            {shown.map((field) => (
              <span className="screenshot-frame__field" key={field.label}>
                <span className="screenshot-frame__label">{field.label}: </span>
                <span className="screenshot-frame__value">{field.value}</span>
              </span>
            ))}
          </span>
        )}
      </header>
      <div className="screenshot-frame__body">{children}</div>
    </div>
  );
}

ScreenshotFrame.propTypes = {
  title: PropTypes.string,
  fields: PropTypes.arrayOf(PropTypes.shape({ label: PropTypes.string, value: PropTypes.string })),
  children: PropTypes.node,
};

ScreenshotFrame.defaultProps = {
  title: null,
  fields: [],
  children: null,
};
