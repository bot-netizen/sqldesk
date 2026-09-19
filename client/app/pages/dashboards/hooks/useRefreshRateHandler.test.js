import { getLimitedRefreshRate, MINIMUM_REFRESH_RATE } from "./useRefreshRateHandler";

jest.mock("@/services/policy", () => ({
  policy: { getDashboardRefreshIntervals: () => [600, 1800, 3600] },
}));

describe("dashboard auto-refresh rate", () => {
  test("never faster than every ten minutes", () => {
    expect(MINIMUM_REFRESH_RATE).toBe(600);
    // An old bookmark with ?refresh=60 is raised, not honoured.
    expect(getLimitedRefreshRate(60)).toBe(600);
    expect(getLimitedRefreshRate(30)).toBe(600);
  });

  test("slower rates are kept", () => {
    expect(getLimitedRefreshRate(1800)).toBe(1800);
  });
});
