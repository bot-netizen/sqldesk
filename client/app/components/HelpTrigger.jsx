import { startsWith, get, some, mapValues } from "lodash";
import React from "react";
import PropTypes from "prop-types";
import cx from "classnames";
import Tooltip from "@/components/Tooltip";
import Drawer from "antd/lib/drawer";
import Link from "@/components/Link";
import PlainButton from "@/components/PlainButton";
import CloseOutlinedIcon from "@ant-design/icons/CloseOutlined";
import BigMessage from "@/components/BigMessage";
import DynamicComponent, { registerComponent } from "@/components/DynamicComponent";

import "./HelpTrigger.less";

// The documentation, which lives in this repository under `docs/` and is
// published by GitHub Pages. Every link here used to point at
// `sqldesk.github.io/sqldesk/help/...` with paths inherited from Redash's
// docs site -- a domain that is not ours and paths that never existed, so
// all twenty-five of them answered 404.
const DOMAIN = "https://bot-netizen.github.io/sqldesk";
const GUIDE = "/guide";
const IFRAME_TIMEOUT = 20000;
const IFRAME_URL_UPDATE_MESSAGE = "iframe_url";

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
  renderAsLink: PropTypes.bool,
  children: PropTypes.node,
};

const HelpTriggerDefaultProps = {
  type: null,
  href: null,
  title: null,
  className: null,
  showTooltip: true,
  renderAsLink: false,
  children: <i className="fa fa-question-circle" aria-hidden="true" />,
};

export function helpTriggerWithTypes(types, allowedDomains = [], drawerClassName = null) {
  return class HelpTrigger extends React.Component {
    static propTypes = {
      ...HelpTriggerPropTypes,
      type: PropTypes.oneOf(Object.keys(types)),
    };

    static defaultProps = HelpTriggerDefaultProps;

    iframeRef = React.createRef();

    iframeLoadingTimeout = null;

    state = {
      visible: false,
      loading: false,
      error: false,
      currentUrl: null,
    };

    componentDidMount() {
      window.addEventListener("message", this.onPostMessageReceived, false);
    }

    componentWillUnmount() {
      window.removeEventListener("message", this.onPostMessageReceived);
      clearTimeout(this.iframeLoadingTimeout);
    }

    loadIframe = (url) => {
      clearTimeout(this.iframeLoadingTimeout);
      this.setState({ loading: true, error: false });

      this.iframeRef.current.src = url;
      this.iframeLoadingTimeout = setTimeout(() => {
        this.setState({ error: url, loading: false });
      }, IFRAME_TIMEOUT); // safety
    };

    onIframeLoaded = () => {
      this.setState({ loading: false });
      clearTimeout(this.iframeLoadingTimeout);
    };

    onPostMessageReceived = (event) => {
      if (!some(allowedDomains, (domain) => startsWith(event.origin, domain))) {
        return;
      }

      const { type, message: currentUrl } = event.data || {};
      if (type !== IFRAME_URL_UPDATE_MESSAGE) {
        return;
      }

      this.setState({ currentUrl });
    };

    getUrl = () => {
      const helpTriggerType = get(types, this.props.type);
      return helpTriggerType ? helpTriggerType[0] : this.props.href;
    };

    openDrawer = (e) => {
      // keep "open in new tab" behavior
      if (!e.shiftKey && !e.ctrlKey && !e.metaKey) {
        e.preventDefault();
        this.setState({ visible: true });
        // wait for drawer animation to complete so there's no animation jank
        setTimeout(() => this.loadIframe(this.getUrl()), 300);
      }
    };

    closeDrawer = (event) => {
      if (event) {
        event.preventDefault();
      }
      this.setState({ visible: false });
      this.setState({ visible: false, currentUrl: null });
    };

    render() {
      const targetUrl = this.getUrl();
      if (!targetUrl) {
        return null;
      }

      const tooltip = get(types, `${this.props.type}[1]`, this.props.title);
      const className = cx("help-trigger", this.props.className);
      const url = this.state.currentUrl;
      const isAllowedDomain = some(allowedDomains, (domain) => startsWith(url || targetUrl, domain));
      const shouldRenderAsLink = this.props.renderAsLink || !isAllowedDomain;

      return (
        <React.Fragment>
          <Tooltip
            title={
              this.props.showTooltip ? (
                <>
                  {tooltip}
                  {shouldRenderAsLink && (
                    <>
                      {" "}
                      <i className="fa fa-external-link" style={{ marginLeft: 5 }} aria-hidden="true" />
                      <span className="sr-only">(opens in a new tab)</span>
                    </>
                  )}
                </>
              ) : null
            }
          >
            <Link
              href={url || this.getUrl()}
              className={className}
              rel="noopener noreferrer"
              target="_blank"
              onClick={shouldRenderAsLink ? () => {} : this.openDrawer}
            >
              {this.props.children}
            </Link>
          </Tooltip>
          <Drawer
            placement="right"
            closable={false}
            onClose={this.closeDrawer}
            visible={this.state.visible}
            className={cx("help-drawer", drawerClassName)}
            destroyOnClose
            width={400}
          >
            <div className="drawer-wrapper">
              <div className="drawer-menu">
                {url && (
                  <Tooltip title="Open page in a new window" placement="left">
                    {/* eslint-disable-next-line react/jsx-no-target-blank */}
                    <Link href={url} target="_blank">
                      <i className="fa fa-external-link" aria-hidden="true" />
                      <span className="sr-only">(opens in a new tab)</span>
                    </Link>
                  </Tooltip>
                )}
                <Tooltip title="Close" placement="bottom">
                  <PlainButton onClick={this.closeDrawer}>
                    <CloseOutlinedIcon />
                  </PlainButton>
                </Tooltip>
              </div>

              {/* iframe */}
              {!this.state.error && (
                <iframe
                  ref={this.iframeRef}
                  title="Usage Help"
                  src="about:blank"
                  className={cx({ ready: !this.state.loading })}
                  onLoad={this.onIframeLoaded}
                />
              )}

              {/* loading indicator */}
              {this.state.loading && (
                <BigMessage icon="fa-spinner fa-2x fa-pulse" message="Loading..." className="help-message" />
              )}

              {/* error message */}
              {this.state.error && (
                <BigMessage icon="fa-exclamation-circle" className="help-message">
                  Something went wrong.
                  <br />
                  {/* eslint-disable-next-line react/jsx-no-target-blank */}
                  <Link href={this.state.error} target="_blank" rel="noopener">
                    Click here
                  </Link>{" "}
                  to open the page in a new window.
                </BigMessage>
              )}
            </div>

            {/* extra content */}
            <DynamicComponent name="HelpDrawerExtraContent" onLeave={this.closeDrawer} openPageUrl={this.loadIframe} />
          </Drawer>
        </React.Fragment>
      );
    }
  };
}

registerComponent("HelpTrigger", helpTriggerWithTypes(TYPES, [DOMAIN]));

export default function HelpTrigger(props) {
  return <DynamicComponent {...props} name="HelpTrigger" />;
}

HelpTrigger.propTypes = HelpTriggerPropTypes;
HelpTrigger.defaultProps = HelpTriggerDefaultProps;
