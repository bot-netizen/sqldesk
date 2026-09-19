import { autoRefreshMaxAge } from "./refreshResults";

describe("auto-refresh", () => {
  test("does not accept the result it made itself last time", () => {
    // Ten-minute refresh: last tick's result is a little under 600 seconds old
    // when this tick fires, and must not count as fresh.
    expect(autoRefreshMaxAge(600)).toBeLessThan(590);
    expect(autoRefreshMaxAge(600)).toBeGreaterThan(0);
  });
});
