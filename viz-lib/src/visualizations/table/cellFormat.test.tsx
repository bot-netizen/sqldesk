import React from "react";
import enzyme from "enzyme";
import {
  cellStyle,
  columnStats,
  dataBarGeometry,
  dataBarIsSigned,
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
    expect(cellStyle(3, f, null)).toEqual({ background: "var(--color-warning-wash, #f7eedd)", color: "#9a6510" });
    expect(cellStyle(5, f, null)!.background).toBe("var(--color-critical-wash, #f8e5e3)");
  });

  test("or the text", () => {
    expect(cellStyle(5, { color: "rules", colorTarget: "text", rules }, null)).toEqual({
      color: "#b4342c",
      fontWeight: 600,
    });
  });

  test("text columns colour by mapping", () => {
    const f = { color: "rules" as const, mappings: [{ value: "down", text: "", color: "critical" }] };
    expect(cellStyle("DOWN", f, null)!.background).toBe("var(--color-critical-wash, #f8e5e3)");
    expect(cellStyle("up", f, null)).toBeUndefined();
  });

  test("a scale deepens from the column's lowest value to its highest", () => {
    const stats = { min: 0, max: 100 };
    expect(cellStyle(0, { color: "scale" }, stats)!.background).toContain(" 6%");
    expect(cellStyle(100, { color: "scale" }, stats)!.background).toContain(" 46%");
    expect(cellStyle("n/a", { color: "scale" }, stats)).toBeUndefined();
  });

  test("column range, against the largest magnitude", () => {
    const stats = columnStats([{ v: -50 }, { v: 25 }, { v: "x" }, { v: null }], "v");
    expect(stats).toEqual({ min: -50, max: 25 });
    expect(columnStats([{ v: "x" }], "v")).toBeNull();
  });

  /*
    The bar used to be the magnitude alone, always growing from the left edge,
    so -90 and 90 drew exactly the same bar. On a column of variances that is
    the one thing the reader needs from it.
  */
  describe("data bars", () => {
    test("a column of positives uses the whole cell, left to right", () => {
      const stats = { min: 0, max: 200 };

      expect(dataBarGeometry(200, stats)).toEqual({ offset: 0, width: 100, negative: false });
      expect(dataBarGeometry(50, stats)).toEqual({ offset: 0, width: 25, negative: false });
      expect(dataBarIsSigned(stats)).toBe(false);
    });

    test("a column of negatives is the mirror of it, growing from the right", () => {
      const stats = { min: -200, max: 0 };

      expect(dataBarGeometry(-200, stats)).toEqual({ offset: 0, width: 100, negative: true });
      expect(dataBarGeometry(-50, stats)).toEqual({ offset: 75, width: 25, negative: true });
      expect(dataBarIsSigned(stats)).toBe(false);
    });

    test("with values on both sides, zero is the middle and the sign is the direction", () => {
      const stats = { min: -100, max: 100 };

      // The largest magnitude reaches the edge, which is half the cell.
      expect(dataBarGeometry(100, stats)).toEqual({ offset: 50, width: 50, negative: false });
      expect(dataBarGeometry(-100, stats)).toEqual({ offset: 0, width: 50, negative: true });
      // And a smaller one starts at the middle either way.
      expect(dataBarGeometry(50, stats)).toEqual({ offset: 50, width: 25, negative: false });
      expect(dataBarGeometry(-50, stats)).toEqual({ offset: 25, width: 25, negative: true });
      expect(dataBarIsSigned(stats)).toBe(true);
    });

    test("the scale is the magnitude, so the longer side sets it", () => {
      // -200 reaches the left edge; +100, half as big, reaches half as far.
      const stats = { min: -200, max: 100 };

      expect(dataBarGeometry(-200, stats)).toEqual({ offset: 0, width: 50, negative: true });
      expect(dataBarGeometry(100, stats)).toEqual({ offset: 50, width: 25, negative: false });
    });

    test("zero itself takes no width and is not negative", () => {
      expect(dataBarGeometry(0, { min: -100, max: 100 })).toEqual({ offset: 50, width: 0, negative: false });
    });

    test("a column that is all zeroes draws nothing rather than dividing by it", () => {
      expect(dataBarGeometry(0, { min: 0, max: 0 })).toEqual({ offset: 0, width: 0, negative: false });
    });

    test("nothing to draw for a value that is not a number", () => {
      expect(dataBarGeometry("n/a", { min: 0, max: 10 })).toBeNull();
      expect(dataBarGeometry(5, null)).toBeNull();
    });
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
    expect(ordersCell(w, "APAC").prop("style").background).toBe("var(--color-critical-wash, #f8e5e3)");
    // rc-table always sets a number column's alignment; the point is no colour.
    expect(ordersCell(w, "EMEA").prop("style").background).toBeUndefined();
    expect(ordersCell(w, "EMEA").find(".table-cell-databar i").prop("style")).toMatchObject({
      // All-positive column: the bar still starts at the left edge.
      left: "0%",
      width: "25%",
    });
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

  test("a data bar keeps its width when the cell also marks a change", () => {
    // The bar measures itself against the cell, so it has to stay outside the
    // change highlight, which shrinks to fit the number. Nested the other way
    // the bar looked right until the first refresh and then collapsed to a
    // sliver behind the digits.
    const o = options({ dataBar: true, showChange: true });
    const w = enzyme.mount(<Renderer data={{ columns, rows }} options={o} />);
    expect(ordersCell(w, "EMEA").find(".table-cell-databar i").prop("style")).toMatchObject({
      // All-positive column: the bar still starts at the left edge.
      left: "0%",
      width: "25%",
    });

    w.setProps({ data: { columns, rows: [{ ...rows[0], orders: 20 }, rows[1]] } });
    w.update();

    const cell = ordersCell(w, "EMEA");
    expect(cell.find(".table-cell-databar i").prop("style")).toMatchObject({ left: "0%", width: "50%" });
    // The bar is the outer element: inside the highlight its percentage would
    // be of the number's width, not the cell's.
    expect(cell.find(".table-cell-changed .table-cell-databar")).toHaveLength(0);
    expect(cell.find(".table-cell-databar .table-cell-changed").length).toBeGreaterThan(0);
    // Twice, because a solid bar restates the number in a readable ink over
    // the filled part, and the two copies carry identical markup so they line
    // up. The second is decorative: hidden from assistive technology, and its
    // highlight is switched off in CSS so the cell flashes once.
    expect(cell.find(".table-cell-changed")).toHaveLength(2);
    expect(cell.find(".table-cell-databar-over").prop("aria-hidden")).toBe("true");
  });

  test("a column with negatives points its bars, and colours them apart", () => {
    // The behaviour the magnitude-only bar could not show: -30 and 30 are the
    // same size and must not look the same.
    const signed = [
      { region: "EMEA", orders: 30, trend: "" },
      { region: "APAC", orders: -30, trend: "" },
    ];
    const o = getOptions({}, { columns, rows: signed });
    o.columns = o.columns.map((c: any) =>
      c.name === "orders"
        ? { ...c, cellFormat: { dataBar: true, dataBarColor: "accent", dataBarNegativeColor: "critical" } }
        : c
    );
    const w = enzyme.mount(<Renderer data={{ columns, rows: signed }} options={o} />);

    const positive = ordersCell(w, "EMEA").find(".table-cell-databar i").prop("style") as any;
    const negative = ordersCell(w, "APAC").find(".table-cell-databar i").prop("style") as any;

    // Both reach the edge from the middle, in opposite directions.
    expect(positive).toMatchObject({ left: "50%", width: "50%" });
    expect(negative).toMatchObject({ left: "0%", width: "50%" });
    expect(positive.background).not.toBe(negative.background);

    // And the zero line is drawn, because this column has two sides.
    expect(ordersCell(w, "EMEA").find(".table-cell-databar-signed")).toHaveLength(1);
  });

  /*
    The bar below zero used to be drawn with no fill at all. Its default
    colour was "danger", which is not one of the six names here and not a CSS
    colour either, so `color-mix(in srgb, danger 16%, transparent)` was
    invalid and the browser threw the whole declaration away. It read as "the
    negative colour is very faint". It was nothing.
  */
  describe("a bar you can actually see", () => {
    const signed = [
      { region: "EMEA", orders: 30, trend: "" },
      { region: "APAC", orders: -30, trend: "" },
    ];

    function signedTable(cellFormat: any) {
      const o = getOptions({}, { columns, rows: signed });
      o.columns = o.columns.map((c: any) => (c.name === "orders" ? { ...c, cellFormat } : c));
      return enzyme.mount(<Renderer data={{ columns, rows: signed }} options={o} />);
    }

    test("a negative bar defaults to a colour that exists", () => {
      const w = signedTable({ dataBar: true });
      const background = (ordersCell(w, "APAC").find(".table-cell-databar i").prop("style") as any).background;

      expect(background).toBeTruthy();
      expect(background).not.toContain("danger");
      expect(background).toBe("var(--color-critical, #b4342c)");
    });

    test("and a column saved before any of this gets the solid fill, not the old wash", () => {
      const w = signedTable({ dataBar: true });
      const positive = (ordersCell(w, "EMEA").find(".table-cell-databar i").prop("style") as any).background;

      expect(positive).toBe("var(--color-action, #0a7c93)");
    });

    test("tinted is still there for anybody who liked it", () => {
      const w = signedTable({ dataBar: true, dataBarFill: "soft" });
      const positive = (ordersCell(w, "EMEA").find(".table-cell-databar i").prop("style") as any).background;

      expect(positive).toBe("var(--color-accent-wash, #e4f4f7)");
    });

    test("the number is restated over the bar in an ink that can be read on it", () => {
      const w = signedTable({ dataBar: true });
      const over = ordersCell(w, "EMEA").find(".table-cell-databar-over");

      expect(over).toHaveLength(1);
      // Clipped to the bar's own rectangle: the bar runs from the middle to
      // the right edge, so the ink does too.
      expect((over.prop("style") as any).clipPath).toBe("inset(0 0% 0 50%)");
      expect((over.prop("style") as any).color).toBe("#ffffff");
    });

    test("a tinted bar gets no second copy, because the cell's own ink reads fine on it", () => {
      const w = signedTable({ dataBar: true, dataBarFill: "soft" });

      expect(ordersCell(w, "EMEA").find(".table-cell-databar-over")).toHaveLength(0);
    });

    test("bars only: the number stays for a screen reader and goes quiet on screen", () => {
      const w = signedTable({ dataBar: true, dataBarShowValue: false });
      const cell = ordersCell(w, "EMEA");

      expect(cell.find(".table-cell-databar-value.is-hidden")).toHaveLength(1);
      expect(cell.find(".table-cell-databar-over")).toHaveLength(0);
      // Still in the DOM, so the value is announced and the row keeps height.
      expect(cell.text()).toContain("30");
    });

    test("a column can be given a floor, because a bar in a narrow column says nothing", () => {
      const w = signedTable({ dataBar: true, dataBarMinWidth: 200 });

      expect((ordersCell(w, "EMEA").prop("style") as any).minWidth).toBe(200);
    });

    test("and is left alone when it has not been given one", () => {
      const w = signedTable({ dataBar: true });

      expect((ordersCell(w, "EMEA").prop("style") as any).minWidth).toBeUndefined();
    });
  });

  test("an all-positive column gets no zero line, so it keeps the whole width", () => {
    const o = options({ dataBar: true });
    const w = enzyme.mount(<Renderer data={{ columns, rows }} options={o} />);

    expect(ordersCell(w, "EMEA").find(".table-cell-databar-signed")).toHaveLength(0);
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
