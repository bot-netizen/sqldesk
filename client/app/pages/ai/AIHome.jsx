import React, { useCallback, useEffect, useState } from "react";
import PropTypes from "prop-types";
import Alert from "antd/lib/alert";
import Button from "antd/lib/button";
import Tag from "antd/lib/tag";

import routeWithUserSession from "@/components/ApplicationArea/routeWithUserSession";
import Link from "@/components/Link";
import { axios } from "@/services/axios";
import { currentUser } from "@/services/auth";
import routes from "@/services/routes";

import "./ai.less";

/*
  The face of `manage ai configure`.

  0.6's AI features are being built; this page is what there is to see in the
  meantime, and it is deliberately not a placeholder. It answers the two
  questions an operator has after running the command -- is it configured, and
  does it answer -- and it says what is coming so the tab is not a promise
  with nothing behind it.

  Two flags, not one. `SQLDESK_FEATURE_AI` is the operator saying they want
  this; a configured provider is there being something to talk to. They fail
  differently and the remedy is different, so the page tells them apart.
*/

const COMING = [
  {
    title: "Context service",
    body:
      "Harvests what each data source knows about itself -- partitions, cardinality, " +
      "distribution keys -- so the rest has something better than a list of column names to work from.",
  },
  {
    title: "Optimize, beside Execute",
    body:
      "Parse, EXPLAIN, and rule packs per engine. The first half finds the expensive mistakes " +
      "without a model at all, and says the same thing every time.",
  },
  {
    title: "MCP server",
    body:
      "One tool layer, so Claude Desktop and the assistant here share the same retrieval, " +
      "the same guards and the same permissions.",
  },
  {
    title: "Semantic layer",
    body:
      "Metric definitions proposed from queries your team already wrote, approved by you, " +
      "and kept as Cube-native YAML you can put in git.",
  },
];

function ProviderPanel({ status, onTest, testing, result }) {
  const provider = status.provider;
  if (!provider) {
    return (
      <div className="ai-panel">
        <h3>No model configured</h3>
        <p className="ai-muted">
          Nothing will be sent anywhere until a provider is named. Run one of these on the server:
        </p>
        <pre className="ai-pre">
          {"manage ai configure anthropic --model claude-sonnet-5 --api-key-stdin\n" +
            "manage ai configure openai --model gpt-4.1 --api-key-stdin\n" +
            "manage ai configure local --base-url http://ollama:11434/v1 --model llama3.1"}
        </pre>
      </div>
    );
  }

  return (
    <div className="ai-panel">
      <h3>
        {provider.type} <span className="ai-muted">/</span> {provider.model}{" "}
        {provider.enabled ? <Tag color="green">enabled</Tag> : <Tag>disabled</Tag>}
      </h3>
      <dl className="ai-facts">
        {provider.base_url && (
          <>
            <dt>Endpoint</dt>
            <dd>{provider.base_url}</dd>
          </>
        )}
        <dt>API key</dt>
        {/* Whether there is one. Never which one -- it does not leave the server. */}
        <dd>{provider.has_api_key ? "stored on the server" : "none (not needed for a local model)"}</dd>
      </dl>
      <Button onClick={onTest} loading={testing} data-test="AITestButton">
        Send a test prompt
      </Button>
      {result && (
        <Alert
          className="m-t-15"
          type={result.ok ? "success" : "error"}
          message={result.ok ? "The model answered" : "The model did not answer"}
          description={result.ok ? result.answer : result.error}
        />
      )}
    </div>
  );
}

ProviderPanel.propTypes = {
  status: PropTypes.object.isRequired, // eslint-disable-line react/forbid-prop-types
  onTest: PropTypes.func.isRequired,
  testing: PropTypes.bool,
  result: PropTypes.object, // eslint-disable-line react/forbid-prop-types
};

ProviderPanel.defaultProps = { testing: false, result: null };

export default function AIHome({ onError }) {
  const [status, setStatus] = useState(null);
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState(null);
  const isAdmin = currentUser.hasPermission("super_admin");

  useEffect(() => {
    let cancelled = false;
    axios
      .get("api/ai/status")
      .then((data) => !cancelled && setStatus(data))
      .catch(onError);
    return () => {
      cancelled = true;
    };
  }, [onError]);

  const test = useCallback(() => {
    setTesting(true);
    setResult(null);
    axios
      .post("api/ai/test")
      .then(setResult)
      .catch(() => setResult({ ok: false, error: "The request failed before it reached the model." }))
      .finally(() => setTesting(false));
  }, []);

  if (!status) {
    return null;
  }

  return (
    <div className="container ai-page" data-test="AIHome">
      <div className="ai-header">
        <h2>AI</h2>
        <p className="ai-muted">
          SQLDesk 0.6 builds its AI on what this instance already knows &mdash; your warehouse, and the queries your
          team has already written. <Link href="https://github.com/bot-netizen/sqldesk">The plan</Link> describes what
          is being built and in what order.
        </p>
      </div>

      {!status.configured && !isAdmin && (
        <Alert
          type="info"
          showIcon
          message="Not configured yet"
          description="An administrator needs to point this instance at a model before the AI features do anything."
        />
      )}

      {isAdmin && <ProviderPanel status={status} onTest={test} testing={testing} result={result} />}

      <h3 className="ai-section-title">What is being built</h3>
      <div className="ai-grid">
        {COMING.map((item) => (
          <div className="ai-card" key={item.title}>
            <h4>{item.title}</h4>
            <p>{item.body}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

AIHome.propTypes = { onError: PropTypes.func };
AIHome.defaultProps = { onError: () => {} };

routes.register(
  "AI.Home",
  routeWithUserSession({
    path: "/ai",
    title: "AI",
    render: (pageProps) => <AIHome {...pageProps} />,
  })
);
