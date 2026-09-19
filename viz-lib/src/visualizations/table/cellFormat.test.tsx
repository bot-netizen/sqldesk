import React from "react";
import enzyme from "enzyme";
import {
  cellStyle,
  columnStats,
  dataBarWidth,
  changeBetween,
  rowIdentity,
  isFormatted,
  normalizeCellFormat,
} from "./cellFormat";
import { parseSeries } from "../shared/columns/sparkline";
import getOptions from "./getOptions";
import Renderer from "./Renderer";
import CellFormatSection from "./Editor/CellFormatSection";
import { TabbedEditor } from "@/components/visualizations/editor/createTabbedEditor";
import ColumnsSettings from "./Editor/ColumnsSettings";

describe("Visualizations -> Table -> cell formatting rules", () => {
  const rules = {
    base: "",
    steps: [
      { value: 2, color: "warning" },
      { value: 4, color: "critical" },
    ],
  };

  test("columns saved before 0.4 are not formatted", () => {
    expect(isFormatted(undefined)).toBe(false);
    expect(cellStyle(9, undefined, null)).toBeUndefined();
  });

  test("threshold rules colour the background, and an empty base leaves low values plain", () => {
    const f = { color: "rules" as const, rules };
    expect(cellStyle(1, f, null)).toBeUndefined();
    expect(cellStyle(3, f, null)).toEqual({ background: "#f7eedd", color: "#9a6510" });
    expect(cellStyle(5, f, null)!.background).toBe("#f8e5e3");
  });

  test("or the text", () => {
    expect(cellStyle(5, { color: "rules", colorTarget: "text", rules }, null)).toEqual({
      color: "#b4342c",
      fontWeight: 600,
    });
  });

  test("text columns colour by mapping", () => {
    const f = { color: "rules" as const, mappings: [{ value: "down", text: "", color: "critical" }] };
    expect(cellStyle("DOWN", f, null)!.background).toBe("#f8e5e3");
    expect(cellStyle("up", f, null)).toBeUndefined();
  });

  test("a scale deepens from the column's lowest value to its highest", () => {
    const stats = { min: 0, max: 100 };
    expect(cellStyle(0, { color: "scale" }, stats)!.background).toContain(" 6%");
    expect(cellStyle(100, { color: "scale" }, stats)!.background).toContain(" 46%");
    expect(cellStyle("n/a", { color: "scale" }, stats)).toBeUndefined();
  });

  test("column range and data bars, against the largest magnitude", () => {
    const stats = columnStats([{ v: -50 }, { v: 25 }, { v: "x" }, { v: null }], "v");
    expect(stats).toEqual({ min: -50, max: 25 });
    expect(dataBarWidth(25, stats)).toBe(50);
    expect(dataBarWidth(-50, stats)).toBe(100);
    expect(columnStats([{ v: "x" }], "v")).toBeNull();
  });

  test("changes between refreshes", () => {
    expect(changeBetween(undefined, 5)).toBeNull(); // a new row
    expect(changeBetween(4, 5)).toBe("up");
    expect(changeBetween(6, 5)).toBe("down");
    expect(changeBetween(5, 5)).toBeNull();
    expect(changeBetween("ok", "down")).toBe("changed");
    expect(changeBetween("ok", "ok")).toBeNull();
  });

  test("rows match by a unique first column, else by position", () => {
    const cols = [{ name: "id" }];
    expect(rowIdentity(cols, [{ id: 1 }, { id: 2 }])({ id: 2 }, 0)).toBe("k:2");
    expect(rowIdentity(cols, [{ id: 1 }, { id: 1 }])({ id: 1 }, 1)).toBe("i:1");
  });

  test("an unknown colour mode is none", () => {
    expect(normalizeCellFormat({ color: "rainbow" as any }).color).toBe("none");
  });
});

describe("Visualizations -> Table -> sparkline cells", () => {
  test.each([
    ["[1, 2, 3]", [1, 2, 3]],
    ["{1,2,3}", [1, 2, 3]],
    ["1, 2 ,3", [1, 2, 3]],
    [
      [1, "2", null, 3],
      [1, 2, 3],
    ],
    ["not a list", []],
    ["[broken", []],
    [null, []],
  ])("parses %p", (input, expected) => {
    expect(parseSeries(input)).toEqual(expected);
  });
});

describe("Visualizations -> Table -> renderer", () => {
  const columns = [
    { name: "region", type: "string" },
    { name: "orders", type: "integer" },
    { name: "trend", type: "string" },
  ];
  const rows = [
    { region: "EMEA", orders: 10, trend: "[1,2,3]" },
    { region: "APAC", orders: 40, trend: "[3,2,1]" },
  ];

  function options(orderFormat: any, trendAs = "string") {
    const o = getOptions({}, { columns, rows });
    o.columns = o.columns.map((c: any) =>
      c.name === "orders" ? { ...c, cellFormat: orderFormat } : c.name === "trend" ? { ...c, displayAs: trendAs } : c
    );
    return o;
  }

  function ordersCell(w: any, region: string) {
    return w
      .find("tr")
      .filterWhere((tr: any) => tr.text().startsWith(region))
      .find("td")
      .at(1);
  }

  test("a formatted column colours its cells and draws bars", () => {
    const o = options({
      color: "rules",
      rules: { base: "", steps: [{ value: 30, color: "critical" }] },
      dataBar: true,
    });
    const w = enzyme.mount(<Renderer data={{ columns, rows }} options={o} />);
    expect(ordersCell(w, "APAC").prop("style").background).toBe("#f8e5e3");
    // rc-table always sets a number column's alignment; the point is no colour.
    expect(ordersCell(w, "EMEA").prop("style").background).toBeUndefined();
    expect(ordersCell(w, "EMEA").find(".table-cell-databar i").prop("style")).toEqual({ width: "25%" });
  });

  test("an unformatted table renders no formatting at all", () => {
    const w = enzyme.mount(<Renderer data={{ columns, rows }} options={options(undefined)} />);
    expect(w.find(".table-cell-databar")).toHaveLength(0);
    expect(ordersCell(w, "APAC").prop("style")).toEqual({ textAlign: "right" });
  });

  test("changed cells are marked after a refresh, matched by the first column", () => {
    const o = options({ showChange: true });
    const w = enzyme.mount(<Renderer data={{ columns, rows }} options={o} />);
    expect(w.find(".table-cell-changed")).toHaveLength(0);

    // Same rows in a different order, one number changed.
    const next = { columns, rows: [{ ...rows[1], orders: 35 }, rows[0]] };
    w.setProps({ data: next });
    w.update();
    const changed = w.find(".table-cell-changed");
    expect(changed).toHaveLength(1);
    expect(changed.hasClass("table-cell-changed-down")).toBe(true);
    expect(changed.text()).toContain("▼");
  });

  test("a sparkline column draws its series", () => {
    const w = enzyme.mount(<Renderer data={{ columns, rows }} options={options(undefined, "sparkline")} />);
    expect(w.find("svg.table-cell-sparkline")).toHaveLength(2);
  });
});

describe("Visualizations -> Table -> editor", () => {
  test("choosing a colour mode stores it on the column", () => {
    const onChange = jest.fn();
    const column = { name: "orders", displayAs: "number" };
    const w = enzyme.mount(<CellFormatSection column={column} onChange={onChange} />);
    w.find('[data-test="Table.Column.orders.CellFormat.DataBar"]')
      .find("input")
      .last()
      .simulate("change", {
        target: { checked: true },
      });
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ name: "orders", cellFormat: expect.objectContaining({ dataBar: true }) })
    );
  });

  test("text columns offer mappings, not thresholds or a scale", () => {
    const w = enzyme.mount(
      <CellFormatSection
        column={{ name: "state", displayAs: "string", cellFormat: { color: "rules" } }}
        onChange={() => {}}
      />
    );
    expect(w.find('[data-test="Table.Column.state.CellFormat.Mappings"]').length).toBeGreaterThan(0);
    expect(w.find('[data-test="Table.Column.state.CellFormat.Thresholds"]')).toHaveLength(0);
  });

  test("removing a rule really removes it: column edits replace, they do not deep-merge", () => {
    const columns = [{ name: "orders", type: "integer" }];
    let options: any = getOptions({}, { columns, rows: [] });
    options.columns[0].cellFormat = {
      color: "rules",
      rules: {
        base: "",
        steps: [
          { value: 1, color: "warning" },
          { value: 2, color: "critical" },
        ],
      },
    };
    const onOptionsChange = jest.fn((next: any) => {
      options = next;
    });
    // Through the real tabbed editor, whose default strategy is a deep merge.
    const w = enzyme.mount(
      <TabbedEditor
        tabs={[{ key: "Columns", title: "Columns", component: ColumnsSettings }] as any}
        {...({ options, data: { columns, rows: [] }, onOptionsChange } as any)}
      />
    );
    // Open the column's panel, then remove the second step.
    w.find(".ant-collapse-header").first().simulate("click");
    w.update();
    w.find('[data-test="Table.Column.orders.CellFormat.Thresholds.Step.1.Remove"]').last().simulate("click");
    expect(options.columns[0].cellFormat.rules.steps).toEqual([{ value: 1, color: "warning" }]);
  });
});
