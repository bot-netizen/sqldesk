import React from "react";
import enzyme from "enzyme";

import getOptions from "../getOptions";
import DataLabelsSettings from "./DataLabelsSettings";

function findByTestID(wrapper: any, testId: any) {
  return wrapper.find(`[data-test="${testId}"]`);
}

function mount(options: any, done: any) {
  options = getOptions(options);
  return enzyme.mount(
    <DataLabelsSettings
      visualizationName="Test"
      data={{ columns: [], rows: [] }}
      options={options}
      onOptionsChange={(changedOptions: any) => {
        expect(changedOptions).toMatchSnapshot();
        done();
      }}
    />
  );
}

describe("Visualizations -> Chart -> Editor -> Data Labels Settings", () => {
  test("Sets Show Data Labels option", (done) => {
    const el = mount(
      {
        globalSeriesType: "column",
        showDataLabels: false,
      },
      done
    );

    findByTestID(el, "Chart.DataLabels.ShowDataLabels")
      .last()
      .find("input")
      .simulate("change", { target: { checked: true } });
  });

  test("Changes number format", (done) => {
    // The numeral format string became a set of controls; what a change now
    // sends up is the whole `ValueFormat`, which is what the renderer reads.
    const el = mount(
      {
        globalSeriesType: "column",
        numberFormat: "0[.]0000",
      },
      done
    );

    findByTestID(el, "Chart.DataLabels.NumberFormat.Suffix")
      .last()
      .simulate("change", { target: { value: " req/s" } });
  });

  test("Changes percent values format", (done) => {
    const el = mount(
      {
        globalSeriesType: "column",
        percentFormat: "0[.]00%",
      },
      done
    );

    findByTestID(el, "Chart.DataLabels.PercentFormat.Decimals")
      .last()
      .simulate("change", { target: { value: "1" } });
  });

  test("a saved numeral format string is read into the controls", (done) => {
    // Existing charts hold a string; the editor has to open on what it means.
    const options = getOptions({ globalSeriesType: "column", numberFormat: "0,0[.]00" });
    expect(options.numberFormat).toEqual(
      expect.objectContaining({ style: "number", decimals: 2, grouping: true, hideZeroFraction: true })
    );
    done();
  });

  test("Changes date/time format", (done) => {
    const el = mount(
      {
        globalSeriesType: "column",
        dateTimeFormat: "YYYY-MM-DD HH:mm:ss",
      },
      done
    );

    findByTestID(el, "Chart.DataLabels.DateTimeFormat")
      .last()
      .simulate("change", { target: { value: "YYYY MMM DD" } });
  });

  test("Changes data labels format", (done) => {
    const el = mount(
      {
        globalSeriesType: "column",
        textFormat: null,
      },
      done
    );

    findByTestID(el, "Chart.DataLabels.TextFormat")
      .last()
      .simulate("change", { target: { value: "{{ @@x }} :: {{ @@y }} / {{ @@yPercent }}" } });
  });
});
