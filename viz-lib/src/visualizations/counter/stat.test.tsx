import React from "react";
import enzyme from "enzyme";
import { getOptions } from "./index";
import { formatCounterValue } from "./utils";
import { orderRows, getStatExtras, headlineIndex } from "./stat";
import Renderer from "./Renderer";
import { act } from "react-dom/test-utils";
import { ENTER_DURATION } from "../shared/motion";

jest.mock("@/services/resizeObserver", () => ({ __esModule: true, default: () => () => {} }));
// The shared barrel pulls in ECharts' ESM build, which babel-jest does not
// transform inside node_modules; the sparkline only needs something to call.
jest.mock("@/visualizations/echarts", () => {
  const chart = { setOption: jest.fn(), resize: jest.fn(), dispose: jest.fn(), on: jest.fn(), off: jest.fn() };
  return { __esModule: true, default: { init: jest.fn(() => chart) } };
});

const columns = [
  { name: "day", type: "date" },
  { name: "orders", type: "integer" },
  { name: "goal", type: "integer" },
];
// Deliberately not in date order.
const rows = [
  { day: "2026-09-03", orders: 110, goal: 100 },
  { day: "2026-09-01", orders: 80, goal: 100 },
  { day: "2026-09-02", orders: 100, goal: 100 },
];

describe("Visualizations -> Stat -> saved counters are unchanged", () => {
  test("a counter being created gets the shared number format", () => {
    expect(getOptions({}).formatMode).toBe("value");
  });

  test("a counter saved before 0.4 keeps the classic one", () => {
    const saved = { counterColName: "a", stringDecimal: 2, stringDecChar: ".", stringThouSep: "," };
    const o = getOptions(saved);
    expect(o.formatMode).toBe("classic");
    // And formats exactly as it always did.
    expect(formatCounterValue(27182.8182846, o)).toBe("27,182.82");
  });

  test("a saved choice of the new format is kept", () => {
    expect(getOptions({ counterColName: "a", formatMode: "value" }).formatMode).toBe("value");
  });

  test("the new format formats through the shared options", () => {
    const o = getOptions({ counterColName: "a", formatMode: "value", valueFormat: { style: "compact" } });
    expect(formatCounterValue(27182.8182846, o)).toBe("27.2K");
  });

  test("new options are all off by default", () => {
    const o = getOptions({ counterColName: "a" });
    expect(o.sparkline.enabled).toBe(false);
    expect(o.comparison.mode).toBe("none");
    expect(o.thresholds.steps).toEqual([]);
  });
});

describe("Visualizations -> Stat -> ordering", () => {
  test("with a sparkline and a time column, rows are read oldest first", () => {
    const o = getOptions({ counterColName: "orders", sparkline: { enabled: true, timeColumn: "day" } });
    expect(orderRows(rows, o, columns).map((r) => r.orders)).toEqual([80, 100, 110]);
  });

  test("an unreadable time goes last instead of vanishing", () => {
    const o = getOptions({ counterColName: "orders", sparkline: { enabled: true, timeColumn: "day" } });
    const withBad = [{ day: "soon", orders: 1 }, ...rows];
    expect(orderRows(withBad, o, columns).map((r) => r.orders)).toEqual([80, 100, 110, 1]);
  });

  test("without a sparkline the query's order and row number stand", () => {
    const o = getOptions({ counterColName: "orders", rowNumber: 2 });
    expect(orderRows(rows, o, columns)).toBe(rows);
    expect(headlineIndex(rows, o)).toBe(1);
  });
});

describe("Visualizations -> Stat -> comparisons", () => {
  const sorted = [rows[1], rows[2], rows[0]]; // 80, 100, 110
  const base = { counterColName: "orders", sparkline: { enabled: true, timeColumn: "day" }, formatMode: "value" };

  test("against the previous row", () => {
    const x = getStatExtras(sorted, getOptions({ ...base, comparison: { mode: "previous" } }), null, "en-US");
    expect(x.delta).toEqual({ text: "▲ 10%", label: "vs previous", tone: "good" });
  });

  test("some rows back, as a difference", () => {
    const x = getStatExtras(
      sorted,
      getOptions({ ...base, comparison: { mode: "rowsBack", rowsBack: 2, display: "absolute" } }),
      null,
      "en-US"
    );
    expect(x.delta).toEqual({ text: "▲ 30", label: "vs 2 rows back", tone: "good" });
  });

  test("against the target column", () => {
    const x = getStatExtras(
      sorted,
      getOptions({ ...base, targetColName: "goal", targetRowNumber: -1, comparison: { mode: "target" } }),
      null,
      "en-US"
    );
    expect(x.delta!.label).toBe("vs target");
    expect(x.delta!.text).toBe("▲ 10%");
  });

  test("a rise can be bad news", () => {
    const x = getStatExtras(sorted, getOptions({ ...base, comparison: { mode: "previous", upIsGood: false } }));
    expect(x.delta!.tone).toBe("critical");
  });

  test("since the last refresh", () => {
    const o = getOptions({ ...base, comparison: { mode: "previousRefresh" } });
    expect(getStatExtras(sorted, o, null).delta).toBeNull();
    expect(getStatExtras(sorted, o, 100, "en-US").delta).toEqual({
      text: "▲ 10%",
      label: "since last refresh",
      tone: "good",
    });
  });

  test("nothing to compare against shows nothing rather than a wrong number", () => {
    const x = getStatExtras([sorted[0]], getOptions({ ...base, comparison: { mode: "previous" } }));
    expect(x.delta).toBeNull();
  });

  test("sparkline points are the value column in order", () => {
    expect(getStatExtras(sorted, getOptions(base)).spark).toEqual([80, 100, 110]);
  });

  test("thresholds colour the number; without them there is no override", () => {
    expect(getStatExtras(sorted, getOptions(base)).valueColor).toBeNull();
    const x = getStatExtras(
      sorted,
      getOptions({ ...base, thresholds: { base: "good", steps: [{ value: 105, color: "critical" }] } })
    );
    expect(x.valueColor).toBe("#b4342c");
  });
});

describe("Visualizations -> Stat -> renderer", () => {
  const data = { columns, rows };

  // The number counts up when it first appears; let it finish.
  beforeEach(() => jest.useFakeTimers());
  afterEach(() => jest.useRealTimers());
  function settle(w: any) {
    act(() => {
      jest.advanceTimersByTime(ENTER_DURATION + 100);
    });
    w.update();
  }

  test("counts up from zero when it first appears", () => {
    const options = getOptions({ counterColName: "orders", formatMode: "value" });
    const w = enzyme.mount(<Renderer data={data} options={options} visualizationName="Orders" />);
    expect(w.find(".counter-visualization-value").text()).toBe("0");

    act(() => {
      jest.advanceTimersByTime(ENTER_DURATION / 2);
    });
    w.update();
    const halfway = Number(w.find(".counter-visualization-value").text());
    expect(halfway).toBeGreaterThan(0);
    expect(halfway).toBeLessThan(110);

    settle(w);
    expect(w.find(".counter-visualization-value").text()).toBe("110");
  });

  test("the latest row is the headline with a sparkline, and the change shows", () => {
    const options = getOptions({
      counterColName: "orders",
      formatMode: "value",
      sparkline: { enabled: true, timeColumn: "day" },
      comparison: { mode: "previous" },
    });
    const w = enzyme.mount(<Renderer data={data} options={options} visualizationName="Orders" />);
    settle(w);
    expect(w.find(".counter-visualization-value").text()).toBe("110");
    expect(w.find('[data-test="Counter.Delta"]').text()).toContain("vs previous");
    expect(w.find(".counter-visualization-sparkline")).toHaveLength(1);
  });

  test("a classic counter renders as before: no badge, no sparkline", () => {
    const options = getOptions({ counterColName: "orders", rowNumber: 1, stringDecimal: 0 });
    const w = enzyme.mount(<Renderer data={data} options={options} visualizationName="Orders" />);
    settle(w);
    expect(w.find(".counter-visualization-value").text()).toBe("110");
    expect(w.find('[data-test="Counter.Delta"]')).toHaveLength(0);
    expect(w.find(".counter-visualization-sparkline")).toHaveLength(0);
  });

  test("'since last refresh' appears after a refresh", () => {
    const options = getOptions({
      counterColName: "orders",
      formatMode: "value",
      comparison: { mode: "previousRefresh" },
    });
    const w = enzyme.mount(<Renderer data={data} options={options} visualizationName="Orders" />);
    expect(w.find('[data-test="Counter.Delta"]')).toHaveLength(0);
    w.setProps({ data: { columns, rows: [{ ...rows[0], orders: 121 }, ...rows.slice(1)] } });
    w.update();
    expect(w.find('[data-test="Counter.Delta"]').text()).toContain("since last refresh");
    expect(w.find(".counter-visualization-delta-badge").text()).toContain("10%");
  });
});
