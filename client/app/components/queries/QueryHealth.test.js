import { getQueryHealth, STALE_INTERVAL_MULTIPLIER } from "./QueryHealth";

const NOW = Date.parse("2026-09-14T12:00:00Z");
const secondsAgo = (n) => new Date(NOW - n * 1000).toISOString();

describe("getQueryHealth", () => {
  test("returns null when stats were not requested, rather than claiming health", () => {
    expect(getQueryHealth({ retrieved_at: secondsAgo(10) }, NOW)).toBeNull();
    expect(getQueryHealth(null, NOW)).toBeNull();
  });

  test("reports failing when there are consecutive schedule failures", () => {
    const health = getQueryHealth({ schedule_failures: 3, retrieved_at: secondsAgo(10) }, NOW);
    expect(health.key).toBe("failing");
    expect(health.tone).toBe("critical");
    expect(health.detail).toContain("3");
  });

  test("failures take precedence over a fresh result", () => {
    const health = getQueryHealth(
      { schedule_failures: 1, retrieved_at: secondsAgo(1), schedule: { interval: 3600 } },
      NOW
    );
    expect(health.key).toBe("failing");
  });

  test("singularises a single failure", () => {
    expect(getQueryHealth({ schedule_failures: 1 }, NOW).detail).toBe("Last 1 scheduled run failed");
  });

  test("reports never-run when there is no result", () => {
    expect(getQueryHealth({ schedule_failures: 0, retrieved_at: null }, NOW).key).toBe("never");
  });

  test("an unscheduled query is never stale, however old", () => {
    const health = getQueryHealth({ schedule_failures: 0, retrieved_at: secondsAgo(86400 * 30) }, NOW);
    expect(health.key).toBe("ok");
  });

  test("a scheduled query goes stale only past the interval multiplier", () => {
    const interval = 3600;
    const query = (age) => ({ schedule_failures: 0, retrieved_at: secondsAgo(age), schedule: { interval } });

    // Comfortably inside the window, and late but within the grace margin.
    expect(getQueryHealth(query(interval), NOW).key).toBe("ok");
    expect(getQueryHealth(query(interval * STALE_INTERVAL_MULTIPLIER - 1), NOW).key).toBe("ok");

    expect(getQueryHealth(query(interval * STALE_INTERVAL_MULTIPLIER + 1), NOW).key).toBe("stale");
  });

  test("treats an explicit zero interval as unscheduled", () => {
    const health = getQueryHealth(
      { schedule_failures: 0, retrieved_at: secondsAgo(86400), schedule: { interval: 0 } },
      NOW
    );
    expect(health.key).toBe("ok");
  });
});
