import { get, mapValues } from "lodash";
import React from "react";
import PropTypes from "prop-types";
import cx from "classnames";
import Tooltip from "@/components/Tooltip";
import Link from "@/components/Link";
import DynamicComponent, { registerComponent } from "@/components/DynamicComponent";

import "./HelpTrigger.less";

// The documentation, which lives in this repository under `docs/` and is
// published by GitHub Pages. Every link here used to point at
// `sqldesk.github.io/sqldesk/help/...` with paths inherited from the upstream
// docs site -- a domain that is not ours and paths that never existed, so
// all twenty-five of them answered 404.
const DOMAIN = "https://bot-netizen.github.io/sqldesk";
const GUIDE = "/guide";

export const TYPES = mapValues(
  {
    HOME: ["/overview.html", "Documentation"],
    GETTING_STARTED: ["/overview.html", "Guide: Getting Started"],
    CONCEPTS: ["/concepts.html", "Guide: Concepts"],
    ARCHITECTURE: ["/architecture.html", "Guide: Architecture"],

    QUERIES: ["/queries.html", "Guide: Queries"],
    VALUE_SOURCE_OPTIONS: ["/queries.html#parameters", "Guide: Parameter Types"],
    MANAGE_PERMISSIONS: ["/queries.html#permissions", "Guide: Query Permissions"],
    FAVORITES: ["/queries.html", "Guide: Queries"],
    SCHEDULES: ["/queries.html#scheduling", "Guide: Scheduling"],

    DASHBOARDS: ["/dashboards.html", "Guide: Dashboards"],
    SHARE_DASHBOARD: ["/dashboards.html#sharing", "Guide: Sharing Dashboards"],
    TEXTBOX_MARKDOWN: ["/dashboards.html#markdown", "Guide: What Markdown Is Allowed"],

    VISUALIZATIONS: ["/visualizations.html", "Guide: Visualizations"],
    NUMBER_FORMAT_SPECS: ["/visualizations.html#numbers", "Guide: Formatting Numbers"],
    LINK_COLUMN: ["/visualizations.html#links", "Guide: Linking From a Chart or Table"],

    ALERTS: ["/alerts.html", "Guide: Alerts"],
    ALERT_SETUP: ["/alerts.html", "Guide: Setting Up an Alert"],
    ALERT_NOTIF_TEMPLATE_GUIDE: ["/alerts.html", "Guide: Custom Alert Notifications"],

    // One page per family rather than one per driver: what people need is
    // the shape of the form and what permission the credential wants, and
    // that is the same answer for every Postgres-like source.
    DS_ATHENA: ["/connectors.html", "Guide: Data Sources"],
    DS_BIGQUERY: ["/connectors.html", "Guide: Data Sources"],
    DS_URL: ["/connectors.html", "Guide: Data Sources"],
    DS_MONGODB: ["/connectors.html", "Guide: Data Sources"],
    DS_GOOGLE_SPREADSHEETS: ["/connectors.html", "Guide: Data Sources"],
    DS_GOOGLE_ANALYTICS: ["/connectors.html", "Guide: Data Sources"],
    DS_AXIBASETSD: ["/connectors.html", "Guide: Data Sources"],
    DS_RESULTS: ["/connectors.html", "Guide: Query Results as a Data Source"],

    MCP: ["/mcp.html", "Guide: MCP"],
    MCP_CONNECT: ["/mcp.html#connecting", "Guide: Connecting a Client"],
    MCP_TOOLS: ["/mcp.html#tools", "Guide: What the Tools Do"],
    MCP_CATALOG: ["/mcp.html#catalog", "Guide: Filling the Catalog"],
    MCP_AUDIT: ["/mcp.html#audit", "Guide: The MCP Audit"],
    MCP_SEMANTIC: ["/mcp.html#semantic", "Guide: Keeping Meaning in Git"],
    MCP_MEASURES: ["/mcp.html#measures", "Guide: Where Measures Come From"],
    AUTHENTICATION_OPTIONS: ["/administration.html", "Guide: Administration"],
    USAGE_DATA_SHARING: ["/administration.html", "Guide: Administration"],
    MAIL_CONFIG: ["/deploying.html", "Guide: Mail Configuration"],
    DEPLOYING: ["/deploying.html", "Guide: Deploying"],
  },
  ([url, title]) => [DOMAIN + GUIDE + url, title]
);

const HelpTriggerPropTypes = {
  type: PropTypes.string,
  href: PropTypes.string,
  title: PropTypes.node,
  className: PropTypes.string,
  showTooltip: PropTypes.bool,
  // Kept so existing callers still validate; every trigger is a link now.
  renderAsLink: PropTypes.bool,
  children: PropTypes.node,
};

const HelpTriggerDefaultProps = {
  type: null,
  href: null,
  title: null,
  className: null,
  showTooltip: true,
  renderAsLink: true,
  children: <i className="fa fa-question-circle" aria-hidden="true" />,
};

/*
  A "?" that opens the page it names in a new tab.

  It used to open a drawer with the page in an iframe. The docs are a whole
  site -- header, navigation, a phone layout below 800px -- and a 400px
  drawer is a phone, so the site's own menu was drawn over the text it was
  meant to explain. A tab shows the page as it was designed, keeps the
  reader's place in SQLDesk, and needs no frame-src in the application's
  security policy.
*/
export function helpTriggerWithTypes(types) {
  function HelpTriggerLink({ type, href, title, className, showTooltip, children }) {
    const entry = get(types, type);
    const url = entry ? entry[0] : href;
    if (!url) {
      return null;
    }
    const tooltip = entry ? entry[1] : title;

    return (
      <Tooltip
        title={
          showTooltip ? (
            <>
              {tooltip} <i className="fa fa-external-link" style={{ marginLeft: 5 }} aria-hidden="true" />
              <span className="sr-only">(opens in a new tab)</span>
            </>
          ) : null
        }
      >
        <Link href={url} className={cx("help-trigger", className)} rel="noopener noreferrer" target="_blank">
          {children}
        </Link>
      </Tooltip>
    );
  }

  HelpTriggerLink.propTypes = {
    ...HelpTriggerPropTypes,
    type: PropTypes.oneOf(Object.keys(types)),
  };
  HelpTriggerLink.defaultProps = HelpTriggerDefaultProps;
  return HelpTriggerLink;
}

registerComponent("HelpTrigger", helpTriggerWithTypes(TYPES));

export default function HelpTrigger(props) {
  return <DynamicComponent {...props} name="HelpTrigger" />;
}

HelpTrigger.propTypes = HelpTriggerPropTypes;
HelpTrigger.defaultProps = HelpTriggerDefaultProps;
