import React from "react";
import enzyme from "enzyme";

import getOptions from "../getOptions";
import EChartsChart from "./EChartsChart";

// jsdom has no ResizeObserver, and the chart only uses it to call resize().
jest.mock("@/services/resizeObserver", () => ({ __esModule: true, default: () => () => {} }));

// The factory is self-contained on purpose. jest.mock is hoisted above this
// file's imports, so a mock defined out here would still be in its temporal
// dead zone when the factory runs during the import of EChartsChart.
//
// Mocking the shared barrel rather than echarts itself: the barrel is what
// pulls in ECharts' ESM build, which babel-jest does not transform inside
// node_modules. buildOption has no echarts import, so the real one runs.
jest.mock("@/visualizations/echarts", () => {
  const chart = {
    setOption: jest.fn(),
    resize: jest.fn(),
    dispose: jest.fn(),
    on: jest.fn(),
    off: jest.fn(),
  };
  return {
    __esModule: true,
    default: { init: jest.fn(() => chart) },
    __chart: chart,
  };
});

const echartsModule = require("@/visualizations/echarts");
const init = echartsModule.default.init;
const chart = echartsModule.__chart;

function chartOptions(overrides: any = {}) {
  return getOptions({
    globalSeriesType: "column",
    sortX: false,
    columnMapping: { x: "x", y: "y" },
    ...overrides,
  });
}

function rows(value: number, x: string = "a") {
  return { columns: [], rows: [{ x, y: value }] };
}

describe("Visualizations -> Chart -> EChartsChart", () => {
  beforeEach(() => {
    init.mockClear();
    chart.setOption.mockClear();
    chart.dispose.mockClear();
  });

  test("creates the chart once and updates it in place when data changes", () => {
    // The whole point of this renderer. The Plotly one called newPlot and
    // destroy() on every data change, so there was never a previous state left
    // to animate from.
    const wrapper = enzyme.mount(<EChartsChart options={chartOptions()} data={rows(2)} />);

    expect(init).toHaveBeenCalledTimes(1);
    expect(chart.setOption).toHaveBeenCalledTimes(1);

    wrapper.setProps({ data: rows(4) });

    expect(init).toHaveBeenCalledTimes(1);
    expect(chart.setOption).toHaveBeenCalledTimes(2);

    wrapper.unmount();
  });

  test("merges the update so ECharts tweens from the old values", () => {
    const wrapper = enzyme.mount(<EChartsChart options={chartOptions()} data={rows(2)} />);

    // Nothing to animate from on first paint, so it replaces.
    expect(chart.setOption.mock.calls[0][1]).toMatchObject({ notMerge: true });

    wrapper.setProps({ data: rows(4) });

    // Same series, same categories: merge, and the bar grows from 2 to 4.
    expect(chart.setOption.mock.calls[1][1]).toMatchObject({ notMerge: false });
    expect(chart.setOption.mock.calls[1][0].series[0].data).toEqual([4]);

    wrapper.unmount();
  });

  test("replaces rather than merges when the categories change", () => {
    const wrapper = enzyme.mount(<EChartsChart options={chartOptions()} data={rows(2)} />);

    wrapper.setProps({ data: rows(9, "b") });

    expect(chart.setOption.mock.calls[1][1]).toMatchObject({ notMerge: true });

    wrapper.unmount();
  });

  test("disposes the chart on unmount", () => {
    const wrapper = enzyme.mount(<EChartsChart options={chartOptions()} data={rows(2)} />);
    wrapper.unmount();

    expect(chart.dispose).toHaveBeenCalledTimes(1);
  });
});
