/*
  A public dashboard is fetched by a token in the URL -- and until this test
  existed, that token was not what decided which dashboard came back.

  The endpoint reads the api key first and only falls back to the token in the
  path when there is no key (sqldesk/handlers/dashboards.py, PublicDashboardResource:
  `if not isinstance(self.current_user, models.ApiUser)`). Every public page
  sets a session key, so on a page showing dashboard A a request for
  dashboard B's URL came back as dashboard A -- a 200, with the wrong body,
  and nothing anywhere to say so.

  That is only reachable when one page asks for two dashboards, which is the
  wall display cycling between them. It cycled for a full minute before this
  was found, because everything else looked right: the timer fired, the
  request went out, the response was a 200.

  So: the token goes in the query string as well as the path. Then the call
  means what it reads like, whatever session it is made from.
*/

jest.mock("@sqldesk/viz/lib", () => ({
  registeredVisualizations: {},
  preloadVisualization: () => {},
}));

const mockGet = jest.fn(() => Promise.resolve({ id: 1, name: "a dashboard", widgets: [] }));

jest.mock("./axios", () => ({
  axios: {
    get: (...args) => mockGet(...args),
  },
}));

const { Dashboard } = require("./dashboard");

const TOKEN = "Vc1z2vAwsMrZf0x6tYqkGpenmewNsaDyVYPTw8tu";

describe("fetching a dashboard by its public token", () => {
  beforeEach(() => mockGet.mockClear());

  test("asks for that token, by path", async () => {
    await Dashboard.getByToken({ token: TOKEN });
    expect(mockGet.mock.calls[0][0]).toBe(`api/dashboards/public/${TOKEN}`);
  });

  test("authenticates as that token, so the answer is the dashboard asked for", async () => {
    await Dashboard.getByToken({ token: TOKEN });
    // Without this the ambient session key decides, and it is whichever
    // dashboard the page opened with.
    expect(mockGet.mock.calls[0][1]).toMatchObject({ params: { api_key: TOKEN } });
  });

  test("the key and the path never disagree", async () => {
    // The failure mode is asking for one dashboard as another, so the two
    // places the token appears have to be the same token.
    await Dashboard.getByToken({ token: TOKEN });
    const [url, config] = mockGet.mock.calls[0];
    expect(url.endsWith(config.params.api_key)).toBe(true);
  });

  test("still transforms the response", async () => {
    // The params argument is the second one; passing it must not have
    // displaced `transformResponse`, which is what turns widgets into Widgets.
    const dashboard = await Dashboard.getByToken({ token: TOKEN });
    expect(dashboard.name).toBe("a dashboard");
    expect(dashboard.widgets).toEqual([]);
  });
});
