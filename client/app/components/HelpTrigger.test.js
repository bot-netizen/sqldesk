import React from "react";
import { mount } from "enzyme";
import { helpTriggerWithTypes, TYPES } from "./HelpTrigger";

// Built the way the application registers it. The drawer version took the
// docs domain as the one it would frame, so a test without it would pass
// against the drawer too.
const HelpTrigger = helpTriggerWithTypes(TYPES, ["https://sqldesk.org"]);

/*
  The "?" opens the docs in a new tab. It used to frame the page in a 400px
  drawer, where the docs site laid itself out for a phone and drew its own
  menu over the text.
*/
describe("HelpTrigger", () => {
  test("links to the page it names, in a new tab", () => {
    const wrapper = mount(<HelpTrigger type="MCP_CONNECT" />);
    const link = wrapper.find("a.help-trigger");

    expect(link.prop("href")).toBe("https://sqldesk.org/guide/mcp.html#connecting");
    expect(link.prop("target")).toBe("_blank");
    expect(link.prop("rel")).toContain("noopener");
  });

  test("lets the browser follow the link rather than opening a drawer", () => {
    // The drawer version cancelled the click to open itself instead.
    const wrapper = mount(<HelpTrigger type="MCP" />);
    const preventDefault = jest.fn();
    wrapper.find("a.help-trigger").simulate("click", { preventDefault });

    expect(preventDefault).not.toHaveBeenCalled();
    expect(wrapper.find("iframe").length).toBe(0);
  });

  test("takes an address of its own when there is no type", () => {
    const wrapper = mount(<HelpTrigger href="https://example.com/page" title="Somewhere" />);
    expect(wrapper.find("a.help-trigger").prop("href")).toBe("https://example.com/page");
  });

  test("renders nothing with neither", () => {
    const wrapper = mount(<HelpTrigger />);
    expect(wrapper.find("a").length).toBe(0);
  });
});
