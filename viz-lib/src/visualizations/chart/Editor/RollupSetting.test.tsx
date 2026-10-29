import React from "react";
import enzyme from "enzyme";

import getOptions from "../getOptions";
import GeneralSettings from "./GeneralSettings";
import { ROLLUPS } from "../rollup";

function findByTestID(wrapper: any, testId: string) {
  return wrapper.find(`[data-test="${testId}"]`);
}

function exists(wrapper: any, testId: string) {
  return findByTestID(wrapper, testId).length > 0;
}

function mount(options: any, onChange: any = () => {}) {
  return enzyme.mount(
    <GeneralSettings
      visualizationName="Test"
      data={{ columns: [], rows: [] }}
      options={getOptions(options)}
      onOptionsChange={onChange}
    />
  );
}

/*
  The roll-up was always happening and never said so. This is the control
  that names it.
*/
describe("Visualizations -> Chart -> Editor -> When rows share an x", () => {
  test("the types that roll up are asked", () => {
    ["column", "line", "area"].forEach((globalSeriesType) => {
      expect(exists(mount({ globalSeriesType }), "Chart.Rollup")).toBe(true);
    });
  });

  test("the types that keep every row are not", () => {
    // A scatter is a point cloud; collapsing it would be the bug, not the
    // feature. Asking a question whose answer is discarded is worse than
    // not asking.
    ["scatter", "pie", "heatmap", "box"].forEach((globalSeriesType) => {
      expect(exists(mount({ globalSeriesType }), "Chart.Rollup")).toBe(false);
    });
  });

  test("it opens on the behaviour that was already there", () => {
    const el = mount({ globalSeriesType: "column" });

    expect(findByTestID(el, "Chart.Rollup").last().props().value).toBe("sum");
  });

  test("a saved choice is what it shows", () => {
    const el = mount({ globalSeriesType: "line", rollup: "average" });

    expect(findByTestID(el, "Chart.Rollup").last().props().value).toBe("average");
  });

  test("choosing one writes it", (done) => {
    const el = mount({ globalSeriesType: "column" }, (changed: any) => {
      expect(changed.rollup).toBe("average");
      done();
    });

    findByTestID(el, "Chart.Rollup").last().simulate("mouseDown");
    findByTestID(el, "Chart.Rollup.average").last().simulate("click");
  });

  test("every mode the module offers is in the dropdown", () => {
    const el = mount({ globalSeriesType: "column" });
    findByTestID(el, "Chart.Rollup").last().simulate("mouseDown");

    ROLLUPS.forEach(({ value }) => expect(exists(el, `Chart.Rollup.${value}`)).toBe(true));
  });

  test("the sentence under it describes the mode that is chosen", () => {
    const el = mount({ globalSeriesType: "column", rollup: "average" });
    const help = ROLLUPS.find((one) => one.value === "average")!.help;

    expect(findByTestID(el, "Chart.Rollup.Help").last().text()).toBe(help);
  });
});
