import React from "react";
import { mount } from "enzyme";
import { act } from "react-dom/test-utils";
import Dropdown from "antd/lib/dropdown";

/*
  The top row is the one piece of UI everybody sees on every page, and three of
  its decisions are not obvious from reading it:

  - what order the places appear in, which is a product decision rather than
    the order the code happens to be written in;
  - who sees each one, which is a permission and not an admin flag -- Catalog
    and the streaming halves are handed to a group by an administrator, and the
    whole point is that the people doing the work are not administrators;
  - that everything which opens a menu looks like it opens a menu.
*/

const mockPermissions = new Set();
const mockFeatures = new Set();

jest.mock("@/services/auth", () => ({
  Auth: { logout: jest.fn() },
  clientConfig: { mcpEnabled: true },
  currentUser: {
    profile_image_url: "",
    hasPermission: (name) => mockPermissions.has(name),
    can: (name) => mockFeatures.has(name),
  },
}));

jest.mock("@/services/axios", () => ({ axios: { get: () => Promise.resolve([]) } }));
jest.mock("@/components/dashboards/CreateDashboardDialog", () => ({ showModal: jest.fn() }));
jest.mock("@/components/ApplicationArea/Router", () => ({
  useCurrentRoute: () => ({ id: "Queries.List" }),
  stripBase: (path) => path,
}));

// eslint-disable-next-line import/first
import DesktopNavbar from "./DesktopNavbar";
// eslint-disable-next-line import/first
import "@/pages/settings.menu";

async function render() {
  let wrapper;
  await act(async () => {
    wrapper = mount(<DesktopNavbar />);
  });
  wrapper.update();
  return wrapper;
}

function places(wrapper) {
  return wrapper
    .find(".desktop-navbar-links")
    .find(".desktop-navbar-link")
    .hostNodes()
    .map((node) => node.text().trim());
}

// antd only renders a dropdown's overlay into the document once it is opened,
// so the menus are read from the element the Dropdown was handed.
function menu(wrapper, which) {
  const dropdown = wrapper
    .findWhere((node) => node.type() === Dropdown && node.find(`[data-test="${which}"]`).exists())
    .first();
  expect(dropdown.exists()).toBe(true);
  return mount(dropdown.prop("overlay"));
}

function linksIn(wrapper, which) {
  return menu(wrapper, which)
    .find("a")
    .map((a) => a.prop("href"));
}

describe("DesktopNavbar", () => {
  beforeEach(() => {
    mockPermissions.clear();
    mockFeatures.clear();
  });

  test("puts the places in the order they were asked for", async () => {
    ["list_dashboards", "view_query", "list_alerts", "super_admin", "admin"].forEach((p) => mockPermissions.add(p));
    ["use_streams", "manage_streams", "manage_catalog"].forEach((f) => mockFeatures.add(f));

    expect(places(await render())).toEqual(["Dashboards", "Queries", "Catalog", "Alerts", "Settings", "Admin"]);
  });

  /*
    No broker's name in the bar.

    Every other item here is named for something you keep -- a dashboard, a
    query, an alert. "Kafka Streams" was named for where the bytes come from,
    which is the same kind of thing as a Postgres tab beside Queries, and it
    made the one capability in SQLDesk that reads as vendor-specific the
    loudest word on every page.
  */
  test("names nothing after the broker it happens to connect to", async () => {
    ["list_dashboards", "view_query", "list_alerts", "super_admin", "admin"].forEach((p) => mockPermissions.add(p));
    ["use_streams", "manage_streams", "manage_catalog"].forEach((f) => mockFeatures.add(f));
    const wrapper = await render();

    expect(wrapper.text()).not.toMatch(/kafka/i);
    expect(places(wrapper)).not.toContain("Kafka Streams");
  });

  test("everything that opens a menu carries the same chevron", async () => {
    ["list_dashboards", "view_query", "super_admin", "admin"].forEach((p) => mockPermissions.add(p));
    mockFeatures.add("use_streams");
    const wrapper = await render();

    ["DashboardsMenuButton", "QueriesMenuButton", "SettingsMenuButton", "AdminMenuButton"].forEach((which) => {
      const button = wrapper.find(`[data-test="${which}"]`).hostNodes();
      expect(button.exists()).toBe(true);
      expect(button.find("i.desktop-navbar-caret").exists()).toBe(true);
    });
  });

  // Alerts goes somewhere; it must not look like it opens a menu.
  test("and a link that goes somewhere does not", async () => {
    mockPermissions.add("list_alerts");
    const wrapper = await render();

    expect(wrapper.find('a[href="alerts"]').find("i.desktop-navbar-caret").exists()).toBe(false);
  });

  /*
    An install with streams switched off -- the chart default -- has no second
    half to offer, and a dropdown holding one item is a click somebody has to
    make to be told there was no choice.
  */
  test("Queries is a plain link where there are no streams to divide it", async () => {
    mockPermissions.add("view_query");
    const wrapper = await render();

    expect(wrapper.find('a[href="queries"]').hostNodes().exists()).toBe(true);
    expect(wrapper.find('[data-test="QueriesMenuButton"]').exists()).toBe(false);
  });

  test("Settings is a named place rather than a gear", async () => {
    mockPermissions.add("admin");
    const wrapper = await render();

    expect(places(wrapper)).toContain("Settings");
    expect(wrapper.find('[data-test="SettingsLink"]').exists()).toBe(false);
  });

  // The whole point of the feature mockPermissions: neither is for everybody, and
  // neither is only for administrators.
  test("Catalog belongs to whoever was granted it, not to admins", async () => {
    mockFeatures.add("manage_catalog");

    expect(places(await render())).toContain("Catalog");
  });

  test("and somebody without it does not see it", async () => {
    mockPermissions.add("admin");
    mockPermissions.add("super_admin");

    expect(places(await render())).not.toContain("Catalog");
  });

  /*
    The two halves of one set, each under the object it is a kind of.

    Not All / Favorites / Mine / Archived as well: those are on the page, and
    putting the cross-product here would be eight entries saying what four
    tabs already say -- with two of them labelled "All".
  */
  test("Queries offers its two halves and nothing else", async () => {
    mockPermissions.add("view_query");
    mockFeatures.add("use_streams");

    expect(linksIn(await render(), "QueriesMenuButton")).toEqual(["queries", "queries/streaming"]);
  });

  test("and Dashboards offers the same two, then the folders", async () => {
    mockPermissions.add("list_dashboards");
    mockFeatures.add("use_streams");

    expect(linksIn(await render(), "DashboardsMenuButton")).toEqual([
      "dashboards",
      "dashboards/streaming",
      "dashboards/folders",
    ]);
  });

  test("and leaves the streaming half out for somebody who may not stream", async () => {
    mockPermissions.add("list_dashboards");

    expect(linksIn(await render(), "DashboardsMenuButton")).toEqual(["dashboards", "dashboards/folders"]);
  });

  /*
    Starting a stream is a create action, not a place. It was the first item of
    a menu of its own -- the only entry in this bar that opened an empty editor
    rather than a list.
  */
  test("starting a stream is in the Create button", async () => {
    mockPermissions.add("create_query");
    mockFeatures.add("use_streams");

    expect(linksIn(await render(), "CreateButton")).toEqual(["queries/new", "streams/query"]);
  });

  test("and is not offered to somebody who may not stream", async () => {
    mockPermissions.add("create_query");

    expect(linksIn(await render(), "CreateButton")).toEqual(["queries/new"]);
  });

  test("the Admin menu reaches every admin page", async () => {
    mockPermissions.add("super_admin");
    const wrapper = await render();
    const adminMenu = menu(wrapper, "AdminMenuButton");

    expect(adminMenu.find("a").map((a) => a.prop("href"))).toEqual([
      "admin/overview",
      "admin/status",
      "admin/queries/jobs",
      "admin/storage",
      "admin/queries/running",
      "admin/streams",
      "admin/audit",
      "admin/queries/outdated",
      "admin/mcp",
    ]);
    // Storage and Streaming Queries had routes and pages for days with no way
    // to reach either, because this menu was written out by hand.
    expect(adminMenu.text()).toContain("Storage Status");
    expect(adminMenu.text()).toContain("Streaming Queries");
  });

  // Eight entries describing themselves in three lines each is a menu taller
  // than the window. The descriptions belong on the pages.
  test("and does not repeat what each page says about itself", async () => {
    mockPermissions.add("super_admin");
    const adminMenu = menu(await render(), "AdminMenuButton");

    expect(adminMenu.text()).not.toContain("Where the headroom is going");
    adminMenu.find("a").forEach((link) => expect(link.text().split(" ").length).toBeLessThanOrEqual(3));
  });

  test("the Settings menu shows only the tabs this person may open", async () => {
    mockPermissions.add("create_query");
    const asUser = linksIn(await render(), "SettingsMenuButton");

    mockPermissions.add("admin");
    mockPermissions.add("list_users");
    const asAdmin = linksIn(await render(), "SettingsMenuButton");

    expect(asUser).toEqual(["query_snippets", "users/me"]);
    expect(asAdmin).toEqual([
      "data_sources",
      "users",
      "groups",
      "destinations",
      "query_snippets",
      "settings/general",
      "users/me",
    ]);
  });

  /*
    Which topics may be queried is a setting on a connection, so it sits beside
    Data Sources rather than in a section of its own -- and it belongs to
    whoever was granted `manage_streams`, who is usually not an administrator.
  */
  test("Streaming Data Sources sits next to Data Sources, for whoever may set topics up", async () => {
    mockPermissions.add("admin");
    mockPermissions.add("list_users");
    mockFeatures.add("manage_streams");

    const links = linksIn(await render(), "SettingsMenuButton");

    expect(links.indexOf("data_sources/streaming")).toBe(links.indexOf("data_sources") + 1);
  });

  test("and is not offered to somebody who may not", async () => {
    mockPermissions.add("admin");
    mockPermissions.add("list_users");

    expect(linksIn(await render(), "SettingsMenuButton")).not.toContain("data_sources/streaming");
  });
});
