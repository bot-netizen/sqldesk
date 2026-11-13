import { axios } from "@/services/axios";
import { currentUser } from "@/services/auth";
import { dashboardWidth, rememberScreen, tableOrders, MAX_WIDTH, MIN_WIDTH } from "./screen";

jest.mock("@/services/axios", () => ({
  axios: { post: jest.fn() },
}));

/*
  The width a dashboard is drawn at on this screen, told to the server so a
  Slack picture of it is the picture Export as image would have made.
*/

function pageWithDashboard(width) {
  document.body.innerHTML = '<div id="dashboard-container"></div>';
  const element = document.getElementById("dashboard-container");
  element.getBoundingClientRect = () => ({ width, height: 600, top: 0, left: 0, right: width, bottom: 600 });
  return document;
}

describe("the dashboard's width on this screen", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  test("is the dashboard container's, to the pixel", () => {
    expect(dashboardWidth(pageWithDashboard(2779.6))).toBe(2780);
  });

  test("is nothing on a page with no dashboard", () => {
    expect(dashboardWidth(document)).toBeNull();
  });

  test("is nothing when it is not a width a picture can be drawn at", () => {
    expect(dashboardWidth(pageWithDashboard(MIN_WIDTH - 1))).toBeNull();
    expect(dashboardWidth(pageWithDashboard(MAX_WIDTH + 1))).toBeNull();
  });
});

describe("telling the server", () => {
  const id = currentUser.id;

  beforeEach(() => {
    currentUser.id = 7;
    axios.post.mockReset();
  });

  afterEach(() => {
    currentUser.id = id;
    document.body.innerHTML = "";
  });

  test("sends the width and this browser's time zone, for this person", async () => {
    axios.post.mockResolvedValue({ screen: {} });

    await rememberScreen({ doc: pageWithDashboard(2780) });

    expect(axios.post).toHaveBeenCalledTimes(1);
    const [url, body] = axios.post.mock.calls[0];
    expect(url).toBe("api/users/7/screen");
    expect(body.width).toBe(2780);
    expect(body.time_zone).toBe(Intl.DateTimeFormat().resolvedOptions().timeZone);
  });

  test("asks nothing where there is no dashboard to measure", async () => {
    await rememberScreen({ doc: document });

    expect(axios.post).not.toHaveBeenCalled();
  });

  test("cannot fail whatever is waiting on it", async () => {
    axios.post.mockRejectedValue(new Error("404"));

    await expect(rememberScreen({ doc: pageWithDashboard(1400) })).resolves.toBeNull();
  });
});

describe("the order each table is in", () => {
  const id = currentUser.id;

  function pageWithTables() {
    document.body.innerHTML = `
      <div id="dashboard-container">
        <div data-widgetid="31"><div data-table-order='[{"name":"slot_requests","direction":"descend"}]'></div></div>
        <div data-widgetid="32"><div data-table-order="[]"></div></div>
        <div data-widgetid="33"><div class="chart"></div></div>
        <div data-widgetid="34"><div data-table-order="not json"></div></div>
      </div>`;
    const element = document.getElementById("dashboard-container");
    element.getBoundingClientRect = () => ({ width: 1400, height: 600, top: 0, left: 0, right: 1400, bottom: 600 });
    return document;
  }

  beforeEach(() => {
    currentUser.id = 7;
    axios.post.mockReset();
    axios.post.mockResolvedValue({});
  });

  afterEach(() => {
    currentUser.id = id;
    document.body.innerHTML = "";
  });

  test("is read off the page, only for tables somebody sorted", () => {
    expect(tableOrders(pageWithTables())).toEqual({
      31: [{ name: "slot_requests", direction: "descend" }],
    });
  });

  test("goes with the screen, for this dashboard", async () => {
    await rememberScreen({ dashboardId: 4, doc: pageWithTables() });

    const body = axios.post.mock.calls[0][1];
    expect(body.dashboard_id).toBe(4);
    expect(body.table_orders).toEqual({ 31: [{ name: "slot_requests", direction: "descend" }] });
    expect(body.width).toBe(1400);
  });

  test("an unsorted dashboard still says so, so an old order is forgotten", async () => {
    document.body.innerHTML = '<div id="dashboard-container"></div>';

    await rememberScreen({ dashboardId: 4, doc: document });

    const body = axios.post.mock.calls[0][1];
    expect(body.table_orders).toEqual({});
  });
});
