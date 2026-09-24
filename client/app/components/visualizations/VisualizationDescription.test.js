import React from "react";
import { mount } from "enzyme";
import VisualizationDescription from "./VisualizationDescription";

/*
  The two things worth pinning: nothing is drawn when there is nothing to say
  (a widget header is crowded enough), and the words are in the document
  rather than only in a tooltip -- which is where the table's column headers
  leave them, unreachable to anyone not using a mouse.
*/

describe("a visualization's description", () => {
  test("is not drawn at all when there is none", () => {
    expect(mount(<VisualizationDescription />).find("button")).toHaveLength(0);
    expect(mount(<VisualizationDescription description="" />).find("button")).toHaveLength(0);
  });

  test("nor when it is only whitespace", () => {
    expect(mount(<VisualizationDescription description="   " />).find("button")).toHaveLength(0);
  });

  test("is readable without a mouse", () => {
    const wrapper = mount(<VisualizationDescription description="Weeks since the account opened." />);

    // In the document, not only in the tooltip the icon raises on hover.
    expect(wrapper.find(".sr-only").text()).toBe("Weeks since the account opened.");
    // And focusable, so a tooltip trigger of "focus" has something to fire on.
    expect(wrapper.find("button")).toHaveLength(1);
  });

  test("is trimmed, so a stray newline is not a description", () => {
    const wrapper = mount(<VisualizationDescription description="  Counts, not sums.  " />);
    expect(wrapper.find(".sr-only").text()).toBe("Counts, not sums.");
  });
});
