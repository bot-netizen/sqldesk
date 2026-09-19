import React from "react";
import enzyme from "enzyme";
import { ThresholdsSection, ValueMappingsSection, ValueFormatSection } from ".";

const byTest = (w: any, id: string) => w.find(`[data-test="${id}"]`);

describe("ThresholdsSection", () => {
  test("adds a step in the next colour up", () => {
    const onChange = jest.fn();
    const w = enzyme.mount(
      <ThresholdsSection thresholds={{ base: "good", steps: [] }} onChange={onChange} testPrefix="T" />
    );
    byTest(w, "T.Thresholds.Add").last().simulate("click");
    expect(onChange).toHaveBeenLastCalledWith({ base: "good", steps: [{ value: 80, color: "warning" }] });
  });

  test("edits and removes one step without touching the others", () => {
    const onChange = jest.fn();
    const thresholds = {
      base: "good",
      steps: [
        { value: 250, color: "warning" },
        { value: 400, color: "critical" },
      ],
    };
    const w = enzyme.mount(<ThresholdsSection thresholds={thresholds} onChange={onChange} testPrefix="T" />);

    byTest(w, "T.Thresholds.Step.0.Value")
      .find("input")
      .last()
      .simulate("change", { target: { value: "300" } });
    expect(onChange).toHaveBeenLastCalledWith({
      base: "good",
      steps: [
        { value: 300, color: "warning" },
        { value: 400, color: "critical" },
      ],
    });

    byTest(w, "T.Thresholds.Step.1.Remove").last().simulate("click");
    expect(onChange).toHaveBeenLastCalledWith({ base: "good", steps: [{ value: 250, color: "warning" }] });
  });
});

describe("ValueMappingsSection", () => {
  test("adds, edits and removes a mapping", () => {
    const onChange = jest.fn();
    const mappings = [{ value: "OK", text: "Healthy", color: "good" }];
    const w = enzyme.mount(<ValueMappingsSection mappings={mappings} onChange={onChange} testPrefix="M" />);

    byTest(w, "M.Mappings.0.Text")
      .find("input")
      .last()
      .simulate("change", { target: { value: "Up" } });
    expect(onChange).toHaveBeenLastCalledWith([{ value: "OK", text: "Up", color: "good" }]);

    byTest(w, "M.Mappings.Add").last().simulate("click");
    expect(onChange).toHaveBeenLastCalledWith([
      { value: "OK", text: "Healthy", color: "good" },
      { value: "", text: "", color: "critical" },
    ]);

    byTest(w, "M.Mappings.0.Remove").last().simulate("click");
    expect(onChange).toHaveBeenLastCalledWith([]);
  });
});

describe("ValueFormatSection", () => {
  test("clearing decimals goes back to automatic rather than zero", () => {
    const onChange = jest.fn();
    const w = enzyme.mount(
      <ValueFormatSection format={{ style: "number", decimals: 2 }} onChange={onChange} testPrefix="F" />
    );
    byTest(w, "F.Decimals")
      .find("input")
      .last()
      .simulate("change", { target: { value: "" } });
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ style: "number", decimals: null }));
  });

  test("shows a preview of the sample value", () => {
    const w = enzyme.mount(
      <ValueFormatSection format={{ style: "compact" }} onChange={() => {}} sampleValue={1234} testPrefix="F" />
    );
    expect(byTest(w, "F.Preview").text()).toContain("1.2K");
  });

  test("currency code only appears for currency", () => {
    const w = enzyme.mount(<ValueFormatSection format={{ style: "number" }} onChange={() => {}} testPrefix="F" />);
    expect(byTest(w, "F.Currency").length).toBe(0);
    w.setProps({ format: { style: "currency" } });
    expect(byTest(w, "F.Currency").length).toBeGreaterThan(0);
  });
});
