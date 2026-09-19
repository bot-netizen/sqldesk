import React from "react";
import enzyme from "enzyme";
import getOptions, { DEFAULT_STATUS_MAPPINGS } from "./getOptions";
import buildTiles from "./buildTiles";
import Renderer from "./Renderer";

const columns = [
  { name: "service", type: "string" },
  { name: "p95", type: "integer" },
  { name: "state", type: "string" },
  { name: "note", type: "string" },
];
const rows = [
  { service: "orders-api", p95: 180, state: "OK", note: "eu-west" },
  { service: "payments", p95: 420, state: "degraded", note: "" },
  { service: "search", p95: 95, state: "Down", note: "failover" },
];
const data = { columns, rows };
const thresholds = {
  base: "good",
  steps: [
    { value: 250, color: "warning" },
    { value: 400, color: "critical" },
  ],
};

function tiles(options: any, d: any = data) {
  return buildTiles(d, getOptions(options, d));
}

describe("Visualizations -> Status Grid -> options", () => {
  test("defaults: text column names the tiles, first number is the value, common words are mapped", () => {
    const o = getOptions({}, data);
    expect(o.nameColumn).toBe("service");
    expect(o.valueColumn).toBe("p95");
    expect(o.mappings).toBe(DEFAULT_STATUS_MAPPINGS);
  });

  test("a status-only result gets no value column", () => {
    const d = { columns: [columns[0], columns[2]], rows: rows.map(({ service, state }) => ({ service, state })) };
    expect(getOptions({}, d).valueColumn).toBe("");
  });
});

describe("Visualizations -> Status Grid -> tiles", () => {
  test("without a status column, thresholds colour by value", () => {
    const { tiles: t } = tiles({ thresholds });
    expect(t.map((x) => x.color)).toEqual(["good", "critical", "good"]);
    expect(t.map((x) => x.status)).toEqual(["Good", "Critical", "Good"]);
  });

  test("a status column wins, through the mappings, ignoring case", () => {
    const { tiles: t } = tiles({ thresholds, statusColumn: "state" });
    expect(t.map((x) => x.color)).toEqual(["good", "warning", "critical"]);
    // The tile says what the query said.
    expect(t.map((x) => x.status)).toEqual(["OK", "degraded", "Down"]);
  });

  test("an unmapped status falls back to the value's thresholds", () => {
    const d = { columns, rows: [{ service: "x", p95: 420, state: "rebooting", note: "" }] };
    expect(tiles({ thresholds, statusColumn: "state" }, d).tiles[0].color).toBe("critical");
  });

  test("a mapping can relabel a value", () => {
    const d = { columns, rows: [{ service: "x", p95: 0, state: "", note: "" }] };
    const t = tiles({ mappings: [{ value: "0", text: "Offline", color: "critical" }] }, d).tiles[0];
    expect(t.value).toBe("Offline");
    expect(t.color).toBe("critical");
  });

  test("values use the value format", () => {
    expect(tiles({ valueFormat: { suffix: " ms" } }).tiles[0].value).toBe("180 ms");
  });

  test("worst first keeps the query's order among equals", () => {
    const d = {
      columns,
      rows: [
        { service: "a", p95: 10, state: "ok" },
        { service: "b", p95: 10, state: "down" },
        { service: "c", p95: 10, state: "ok" },
        { service: "d", p95: 10, state: "warn" },
      ],
    };
    expect(tiles({ statusColumn: "state", sort: "severity" }, d).tiles.map((x) => x.name)).toEqual([
      "b",
      "d",
      "a",
      "c",
    ]);
  });

  test("by name sorts numbers naturally", () => {
    const d = { columns, rows: ["node-10", "node-2", "node-1"].map((service) => ({ service, p95: 1 })) };
    expect(tiles({ sort: "name" }, d).tiles.map((x) => x.name)).toEqual(["node-1", "node-2", "node-10"]);
  });

  test("repeated names still get distinct keys", () => {
    const d = {
      columns,
      rows: [
        { service: "a", p95: 1 },
        { service: "a", p95: 2 },
      ],
    };
    expect(tiles({}, d).tiles.map((x) => x.key)).toEqual(["a", "a#2"]);
  });

  test("problems", () => {
    expect(tiles({}, { columns, rows: [] }).problem).toMatch(/No rows/);
    expect(tiles({ valueColumn: "", statusColumn: "" }).problem).toMatch(/Choose a value column or a status column/);
  });
});

describe("Visualizations -> Status Grid -> renderer", () => {
  test("outlines a tile when its state changes, and only that tile", () => {
    const options = getOptions({ thresholds }, data);
    const w = enzyme.mount(<Renderer data={data} options={options} />);
    expect(w.find(".status-grid-tile-changed")).toHaveLength(0);

    const next = { columns, rows: rows.map((r) => (r.service === "orders-api" ? { ...r, p95: 300 } : r)) };
    w.setProps({ data: next });
    w.update();
    const changed = w.find(".status-grid-tile-changed");
    expect(changed).toHaveLength(1);
    expect(changed.prop("data-test")).toBe("StatusGrid.Tile.orders-api");
  });

  test("a value change that stays in the same band is not a state change", () => {
    const options = getOptions({ thresholds }, data);
    const w = enzyme.mount(<Renderer data={data} options={options} />);
    w.setProps({ data: { columns, rows: rows.map((r) => ({ ...r, p95: r.p95 + 1 })) } });
    w.update();
    expect(w.find(".status-grid-tile-changed")).toHaveLength(0);
  });
});
