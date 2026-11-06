const mockPermissions = new Set(["list_dashboards", "create_dashboard"]);

jest.mock("@/services/auth", () => ({
  Auth: { getApiKey: () => null, isAuthenticated: () => true },
  clientConfig: { pageSizeOptions: [25, 50, 100] },
  currentUser: {
    id: 1,
    name: "Iqbal",
    profile_image_url: "",
    hasPermission: (name) => mockPermissions.has(name),
    can: () => false,
  },
}));

jest.mock("@/services/axios", () => ({
  axios: {
    get: () => Promise.resolve([]),
    post: () => Promise.resolve({}),
    delete: () => Promise.resolve({}),
    interceptors: { request: { use: () => {} }, response: { use: () => {} } },
  },
}));

jest.mock("@/components/ApplicationArea/routeWithUserSession", () => ({
  __esModule: true,
  default: (route) => route,
}));

// eslint-disable-next-line import/first
import { mount } from "enzyme";
// eslint-disable-next-line import/first
import { Dashboard } from "@/services/dashboard";
// eslint-disable-next-line import/first
import routes from "@/services/routes";
// eslint-disable-next-line import/first
import { viewsFor } from "./DashboardList";

/*
  The two halves of the dashboards list, and the one place they meet.

  A dashboard shows streams or saved queries and never both, so it belongs to
  exactly one half. `?kind=` therefore has to ride on all three views, not only
  the plain list -- it used to be on the plain list alone, which left Mine and
  Favorites showing both kinds.

  A folder is the exception, deliberately: it is a place rather than a type, so
  it shows whatever is filed in it. That is the only list where the halves meet
  and it has to keep working that way, or filing a streaming dashboard in a
  folder would hide it from the folder.
*/
async function settle(wrapper, times = 3) {
  for (let index = 0; index < times; index += 1) {
    // eslint-disable-next-line no-await-in-loop
    await new Promise((resolve) => setTimeout(resolve, 0));
    wrapper.update();
  }
}

const EMPTY = { results: [], count: 0, page: 1, page_size: 25 };

function routeFor(id) {
  const route = routes.items.find((item) => item.id === id);
  expect(route).toBeDefined();
  return route;
}

async function render(routeId, routeProps = {}) {
  const wrapper = mount(routeFor(routeId).render(routeProps));
  await settle(wrapper);
  return wrapper;
}

describe("the dashboards list", () => {
  beforeEach(() => {
    jest.spyOn(Dashboard, "query").mockResolvedValue(EMPTY);
    jest.spyOn(Dashboard, "myDashboards").mockResolvedValue(EMPTY);
    jest.spyOn(Dashboard, "favorites").mockResolvedValue(EMPTY);
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  test("the ordinary half asks for the ordinary dashboards", async () => {
    await render("Dashboards.List");

    expect(Dashboard.query).toHaveBeenCalledWith(expect.objectContaining({ kind: "saved" }));
  });

  test("and the streaming half asks for the other kind", async () => {
    await render("Dashboards.Streaming");

    expect(Dashboard.query).toHaveBeenCalledWith(expect.objectContaining({ kind: "streaming" }));
  });

  test.each([
    ["Dashboards.StreamingMy", () => Dashboard.myDashboards],
    ["Dashboards.StreamingFavorites", () => Dashboard.favorites],
  ])("%s carries the kind as well", async (routeId, resource) => {
    await render(routeId);

    expect(resource()).toHaveBeenCalledWith(expect.objectContaining({ kind: "streaming" }));
  });

  test("a folder asks for no kind, because it holds both", async () => {
    await render("Dashboards.Folder", { folderId: 4 });

    expect(Dashboard.query).toHaveBeenCalledWith(expect.objectContaining({ folder: 4 }));
    expect(Dashboard.query).not.toHaveBeenCalledWith(expect.objectContaining({ kind: expect.anything() }));
  });

  test("the views stay inside the half you are looking at", () => {
    expect(viewsFor("streaming").map((view) => view.href)).toEqual([
      "dashboards/streaming",
      "dashboards/streaming/favorites",
      "dashboards/streaming/my",
      "dashboards/streaming/archive",
    ]);
  });

  test("and in the ordinary half they are the paths they always were", () => {
    expect(viewsFor("saved").map((view) => view.href)).toEqual([
      "dashboards",
      "dashboards/favorites",
      "dashboards/my",
      "dashboards/archive",
    ]);
  });

  // A folder page names no half, and must not be shown the streaming one.
  test("and a page that names neither gets the ordinary paths", () => {
    expect(viewsFor(undefined).map((view) => view.href)).toEqual(viewsFor("saved").map((view) => view.href));
  });
});
