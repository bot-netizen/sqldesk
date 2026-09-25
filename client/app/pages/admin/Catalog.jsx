import React, { useCallback, useEffect, useMemo, useState } from "react";
import Alert from "antd/lib/alert";
import Button from "antd/lib/button";
import Input from "antd/lib/input";
import Select from "antd/lib/select";
import Switch from "antd/lib/switch";
import Table from "antd/lib/table";
import Tag from "antd/lib/tag";

import routeWithUserSession from "@/components/ApplicationArea/routeWithUserSession";
import Layout from "@/components/admin/Layout";
import HelpTrigger from "@/components/HelpTrigger";
import { axios } from "@/services/axios";
import notification from "@/services/notification";
import routes from "@/services/routes";

import "./catalog.less";

/*
  Reviewing what the MCP tools will say about your warehouse.

  Sorted by usage and filtered to the undescribed, because the job is
  otherwise impossible: nobody writes three thousand sentences, and the
  twenty tables anyone actually queries are most of the value. The point of
  the page is to make the work finite.
*/

function DescriptionCell({ table, onSaved }) {
  const [value, setValue] = useState(table.description || "");
  const [saving, setSaving] = useState(false);
  const dirty = value !== (table.description || "");

  const save = useCallback(() => {
    setSaving(true);
    axios
      .post(`api/admin/catalog/tables/${table.id}`, { description: value })
      .then((saved) => {
        onSaved(table.id, saved);
        notification.success(`Described ${table.name}.`);
      })
      .catch(() => notification.error("Could not save that."))
      .finally(() => setSaving(false));
  }, [table.id, table.name, value, onSaved]);

  return (
    <div className="catalog-describe">
      <Input.TextArea
        rows={2}
        value={value}
        placeholder="What is this table for? What is a row? What should nobody trust?"
        onChange={(event) => setValue(event.target.value)}
      />
      <div className="catalog-describe-actions">
        {/* Where the sentence came from, because it decides what happens to
            it next: a harvest may replace the engine's, never a person's. */}
        {table.description_source === "human" && <Tag>yours</Tag>}
        {table.description_source === "engine" && <Tag color="blue">from the warehouse</Tag>}
        <Button size="small" type="primary" disabled={!dirty} loading={saving} onClick={save}>
          Save
        </Button>
      </div>
    </div>
  );
}

export default function Catalog() {
  const [tables, setTables] = useState([]);
  const [sources, setSources] = useState([]);
  const [sourceId, setSourceId] = useState(null);
  const [undescribed, setUndescribed] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    const params = [];
    if (sourceId) {
      params.push(`data_source_id=${sourceId}`);
    }
    if (undescribed) {
      params.push("undescribed=1");
    }
    axios
      .get(`api/admin/catalog${params.length ? `?${params.join("&")}` : ""}`)
      .then((data) => setTables(data.tables))
      .catch(() => notification.error("Could not load the catalog."))
      .finally(() => setLoading(false));
  }, [sourceId, undescribed]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    axios
      .get("api/data_sources")
      .then(setSources)
      .catch(() => {});
  }, []);

  const onSaved = useCallback((id, saved) => {
    setTables((current) =>
      current.map((table) =>
        table.id === id
          ? { ...table, description: saved.description, description_source: saved.description_source }
          : table
      )
    );
  }, []);

  const missing = useMemo(() => tables.filter((table) => !table.description).length, [tables]);

  const columns = [
    {
      title: "Table",
      dataIndex: "name",
      width: 260,
      render: (name, row) => (
        <div>
          <div className="catalog-name">{name}</div>
          <div className="catalog-muted">{row.column_count} columns</div>
        </div>
      ),
    },
    {
      title: "Used by",
      dataIndex: "usage_count",
      width: 110,
      align: "right",
      // The ranking signal, and worth showing rather than only sorting by:
      // it is the answer to "is this worth my time to describe".
      render: (count) => (count ? `${count} queries` : <span className="catalog-muted">—</span>),
    },
    {
      title: "What it is for",
      dataIndex: "description",
      render: (_, row) => <DescriptionCell table={row} onSaved={onSaved} />,
    },
  ];

  return (
    <Layout activeTab="catalog">
      <div className="p-15 catalog-page" data-test="AdminCatalog">
        <div className="catalog-header">
          <h3>
            Catalog <HelpTrigger type="MCP_CATALOG" />
          </h3>
          <p className="catalog-muted">
            What the MCP tools know about your warehouse. Structure and usage are harvested; what a table is{" "}
            <em>for</em> is the part only a person can write.
          </p>
        </div>

        <div className="catalog-controls">
          <Select
            allowClear
            className="catalog-source"
            placeholder="Every data source"
            value={sourceId}
            onChange={setSourceId}
            options={sources.map((source) => ({ value: source.id, label: source.name }))}
          />
          <span className="catalog-toggle">
            <Switch
              size="small"
              checked={undescribed}
              onChange={setUndescribed}
              aria-label="Show only tables with no description"
            />{" "}
            Only ones still missing a description
          </span>
          <Button size="small" onClick={load} loading={loading}>
            Refresh
          </Button>
        </div>

        {!loading && tables.length === 0 && (
          <Alert
            type="info"
            showIcon
            message="Nothing harvested yet"
            description="The catalog fills on a schedule, or immediately with `manage ai harvest`."
          />
        )}

        {tables.length > 0 && missing > 0 && !undescribed && (
          <p className="catalog-muted catalog-count">
            {missing} of these {tables.length} have no description.
          </p>
        )}

        <Table
          className="catalog-table"
          dataSource={tables}
          columns={columns}
          rowKey="id"
          size="small"
          loading={loading}
          pagination={{ pageSize: 20, showSizeChanger: false }}
        />
      </div>
    </Layout>
  );
}

routes.register(
  "Admin.Catalog",
  routeWithUserSession({
    path: "/admin/catalog",
    title: "Catalog",
    render: (pageProps) => <Catalog {...pageProps} />,
  })
);
