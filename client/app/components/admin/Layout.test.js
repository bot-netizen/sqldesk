import React from "react";
import { mount } from "enzyme";

/*
  The tab strip, and the thing it gained: a description under it.

  Both menus that reach these pages are drawn from one list now, so this is
  where that list is checked -- the keys the pages pass as `activeTab` have to
  be the keys in it, or a page highlights nothing and shows no description
  while still looking perfectly fine.
*/
jest.mock("@/services/auth", () => ({ clientConfig: { mcpEnabled: true }, currentUser: {} }));

// eslint-disable-next-line import/first
import { clientConfig } from "@/services/auth";
// eslint-disable-next-line import/first
import Layout from "./Layout";
// eslint-disable-next-line import/first
import { adminTabs } from "@/pages/admin/adminTabs";

function titles(wrapper) {
  return wrapper
    .find(".ant-menu-item")
    .hostNodes()
    .map((item) => item.text().trim());
}

describe("admin Layout", () => {
  beforeEach(() => {
    clientConfig.mcpEnabled = true;
  });

  test("shows every admin page, in order", () => {
    expect(titles(mount(<Layout activeTab="overview" />))).toEqual([
      "Overview",
      "System Status",
      "RQ Status",
      "Storage Status",
      "Running Queries",
      "Streaming Queries",
      "Audit",
      "Outdated Queries",
      "MCP",
    ]);
  });

  test("leaves MCP out when this install has it switched off", () => {
    clientConfig.mcpEnabled = false;

    expect(titles(mount(<Layout activeTab="overview" />))).not.toContain("MCP");
    expect(adminTabs().map((tab) => tab.key)).not.toContain("mcp");
  });

  test("says what the page you are on is", () => {
    const wrapper = mount(<Layout activeTab="storage" />);

    expect(wrapper.find(".admin-tab-description").text()).toContain("What SQLDesk is holding");
  });

  // Every page passes its own key. One that does not match the list silently
  // loses both its highlight and its description.
  test("and every page's key is one of the tabs", () => {
    const keys = adminTabs().map((tab) => tab.key);

    ["overview", "running_queries", "system_status", "jobs", "outdated_queries", "storage", "streams", "mcp"].forEach(
      (passedByAPage) => {
        expect(keys).toContain(passedByAPage);
        expect(
          mount(<Layout activeTab={passedByAPage} />)
            .find(".admin-tab-description")
            .exists()
        ).toBe(true);
      }
    );
  });

  test("marks the tab you are on", () => {
    const wrapper = mount(<Layout activeTab="jobs" />);

    expect(wrapper.find(".ant-menu-item-selected").hostNodes().text().trim()).toBe("RQ Status");
  });

  // It used to render its own page, outside the tab strip, so opening it was a
  // one-way trip: nothing on screen led back to the other admin pages.
  test("MCP is a tab like the rest, not a page of its own", () => {
    const wrapper = mount(<Layout activeTab="mcp" />);

    expect(wrapper.find(".ant-menu-item-selected").hostNodes().text().trim()).toBe("MCP");
    expect(titles(wrapper)).toContain("Overview");
  });

  test("every tab describes itself in more than a title", () => {
    adminTabs().forEach((tab) => {
      expect(tab.description.length).toBeGreaterThan(80);
    });
  });
});

/*
  Each admin tab used to pad itself, and they disagreed: System Status 15px
  all round, Storage and Streams vertically only, Audit and Catalog not at
  all. So Audit's date picker started at the panel's edge while the caption
  directly above it was inset, and the totals box ran into the rounded
  corner.

  One wrapper owns the padding now, which is what keeps the tabs agreeing.
*/
describe("where a tab's content sits", () => {
  test("every tab's content goes in one padded wrapper", () => {
    const wrapper = mount(
      <Layout activeTab="audit">
        <div className="whatever-the-tab-draws" />
      </Layout>
    );

    const content = wrapper.find(".admin-tab-content");
    expect(content.exists()).toBe(true);
    expect(content.find(".whatever-the-tab-draws").exists()).toBe(true);
  });

  test("the caption stays outside it, so the two are not inset twice", () => {
    const wrapper = mount(
      <Layout activeTab="audit">
        <div />
      </Layout>
    );

    expect(wrapper.find(".admin-tab-content .admin-tab-description").exists()).toBe(false);
    expect(wrapper.find(".admin-tab-description").exists()).toBe(true);
  });
});
