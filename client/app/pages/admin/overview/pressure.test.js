import { pressure, formatBytes, formatElapsed, formatRatio, OK, WATCH, CRITICAL, UNKNOWN } from "./pressure";

/*
  The arithmetic behind the admin overview's bars. Tested apart from the
  drawing because this is the half that can be wrong without anyone noticing:
  a missing bar is obvious, a threshold quietly off by a factor of ten is not.
*/

describe("pressure", () => {
  test("is quiet well below the limit", () => {
    expect(pressure(10, 100).level).toBe(OK);
  });

  test("says watch at three quarters", () => {
    expect(pressure(74, 100).level).toBe(OK);
    expect(pressure(75, 100).level).toBe(WATCH);
  });

  test("says critical at nine tenths", () => {
    expect(pressure(89, 100).level).toBe(WATCH);
    expect(pressure(90, 100).level).toBe(CRITICAL);
  });

  test("reports the fraction as well as the level", () => {
    expect(pressure(25, 100).fraction).toBe(0.25);
  });

  test("a missing limit is not a limit of zero", () => {
    // Redis reports maxmemory as 0 when none is configured, which means "as
    // much as the machine has". Reading that as a limit would put every
    // install permanently at 100%.
    expect(pressure(500, 0).level).toBe(UNKNOWN);
    expect(pressure(500, null).level).toBe(UNKNOWN);
    expect(pressure(500, undefined).fraction).toBeNull();
  });

  test("nothing measured is not nothing used", () => {
    expect(pressure(null, 100).level).toBe(UNKNOWN);
  });

  test("over the limit is still critical, not an error", () => {
    // Postgres can report more connections than max_connections, because
    // superuser_reserved_connections sit outside it.
    expect(pressure(105, 100).level).toBe(CRITICAL);
  });
});

describe("formatBytes", () => {
  test.each([
    [0, "0 B"],
    [512, "512 B"],
    [1024, "1.0 kB"],
    [1536, "1.5 kB"],
    [1024 * 1024, "1.0 MB"],
    [1024 * 1024 * 1024 * 3, "3.0 GB"],
  ])("%s bytes reads as %s", (bytes, expected) => {
    expect(formatBytes(bytes)).toBe(expected);
  });

  test("says nothing rather than NaN", () => {
    expect(formatBytes(undefined)).toBe("—");
    expect(formatBytes(-1)).toBe("—");
  });
});

describe("formatElapsed", () => {
  test("counts seconds while seconds are the question", () => {
    // 3s against 40s is the whole point; 61m against 62m is not.
    expect(formatElapsed(3)).toBe("3s");
    expect(formatElapsed(59.6)).toBe("59s");
  });

  test("counts minutes after that", () => {
    expect(formatElapsed(60)).toBe("1m 0s");
    expect(formatElapsed(272)).toBe("4m 32s");
  });

  test("counts hours after that", () => {
    expect(formatElapsed(3600)).toBe("1h 0m");
    expect(formatElapsed(3600 * 2 + 60 * 13)).toBe("2h 13m");
  });

  test("says nothing rather than NaN", () => {
    expect(formatElapsed(null)).toBe("—");
  });
});

describe("formatRatio", () => {
  test("reads as a percentage", () => {
    expect(formatRatio(0.615)).toBe("62%");
    expect(formatRatio(1)).toBe("100%");
  });

  test("a ratio of nothing is a dash, not zero", () => {
    // No executions means the question does not apply, not that every lookup
    // missed.
    expect(formatRatio(null)).toBe("—");
  });
});
