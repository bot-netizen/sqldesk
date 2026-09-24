import React from "react";
import { mount } from "enzyme";
import TextboxWidget from "./TextboxWidget";

jest.mock("@/services/recordEvent", () => jest.fn());
jest.mock("@/components/dashboards/TextboxDialog", () => ({ showModal: jest.fn() }));

function widget(text, options = {}) {
  return { id: 1, text, width: 1, options, save: jest.fn(() => Promise.resolve()) };
}

/*
  A textbox is how a dashboard is divided into sections. The thing worth
  pinning is that turning its tile off actually turns it off -- a heading in
  a white card with fifty empty pixels under it is what this exists to stop.
*/

describe("a textbox widget", () => {
  test("is a tile by default, as every widget saved before this was", () => {
    const wrapper = mount(<TextboxWidget widget={widget("## Hello")} />);
    expect(wrapper.find(".tile").hasClass("widget-text-card")).toBe(true);
  });

  test("drops the tile when it is set to plain", () => {
    const wrapper = mount(<TextboxWidget widget={widget("## Hello", { textStyle: "plain" })} />);
    expect(wrapper.find(".tile").hasClass("widget-text-plain")).toBe(true);
  });

  test("renders markdown the new library understands", () => {
    const wrapper = mount(<TextboxWidget widget={widget("| a |\n|---|\n| 1 |")} />);
    expect(wrapper.html()).toContain("<table>");
  });

  test("takes the alignment it was given", () => {
    const wrapper = mount(<TextboxWidget widget={widget("centred", { align: "center" })} />);
    expect(wrapper.find("div.markdown").prop("style")).toEqual({ textAlign: "center" });
  });

  test("an option it does not recognise falls back rather than breaking the tile", () => {
    const wrapper = mount(<TextboxWidget widget={widget("x", { textStyle: "nonsense", align: "diagonal" })} />);
    expect(wrapper.find(".tile").hasClass("widget-text-card")).toBe(true);
    expect(wrapper.find("div.markdown").prop("style")).toEqual({ textAlign: "left" });
  });

  test("a widget with no width is not drawn at all", () => {
    const w = widget("x");
    w.width = 0;
    expect(mount(<TextboxWidget widget={w} />).html()).toBeNull();
  });
});
