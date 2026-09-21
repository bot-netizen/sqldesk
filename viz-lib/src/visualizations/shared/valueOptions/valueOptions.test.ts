import {
  formatValue,
  computeDelta,
  formatDelta,
  thresholdColor,
  thresholdBands,
  normalizeThresholds,
  findMapping,
  resolveColor,
  washColor,
  SEMANTIC_COLORS,
  SEMANTIC_COLOR_NAMES,
  EMPTY_VALUE,
} from ".";

// Pinned so the tests do not depend on the machine's locale.
const L = "en-US";

describe("formatValue", () => {
  test("missing values read as a dash, not as zero", () => {
    expect(formatValue(null, {}, L)).toBe(EMPTY_VALUE);
    expect(formatValue(undefined, {}, L)).toBe(EMPTY_VALUE);
    expect(formatValue("", {}, L)).toBe(EMPTY_VALUE);
  });

  test("text passes through without the prefix or suffix", () => {
    // A status column saying "Down" must not grow a currency sign.
    expect(formatValue("Down", { style: "currency", prefix: "~", suffix: " ms" }, L)).toBe("Down");
  });

  test("numeric strings are numbers", () => {
    // Several drivers return decimals as strings.
    expect(formatValue("1234.5", { style: "number", decimals: 2 }, L)).toBe("1,234.50");
  });

  test("automatic keeps integers whole and trims long fractions", () => {
    expect(formatValue(1234, {}, L)).toBe("1,234");
    expect(formatValue(3.14159, {}, L)).toBe("3.14");
    expect(formatValue(1234.567, {}, L)).toBe("1,234.6");
  });

  test("fixed decimals pad as well as round", () => {
    expect(formatValue(2, { style: "number", decimals: 2 }, L)).toBe("2.00");
    expect(formatValue(2.005, { style: "auto", decimals: 0 }, L)).toBe("2");
  });

  test("compact", () => {
    expect(formatValue(1234, { style: "compact" }, L)).toBe("1.2K");
    expect(formatValue(5_600_000, { style: "compact" }, L)).toBe("5.6M");
  });

  test("percent takes a fraction", () => {
    expect(formatValue(0.256, { style: "percent" }, L)).toBe("25.6%");
    expect(formatValue(0.256, { style: "percent", decimals: 0 }, L)).toBe("26%");
  });

  test("currency, and an unknown code does not blank the value", () => {
    expect(formatValue(1234.5, { style: "currency", currency: "USD" }, L)).toBe("$1,234.50");
    expect(formatValue(1234.5, { style: "currency", currency: "not-a-code" }, L)).toBe("1,234.5");
  });

  test("bytes scale by 1024", () => {
    expect(formatValue(512, { style: "bytes" }, L)).toBe("512 B");
    expect(formatValue(1536, { style: "bytes" }, L)).toBe("1.5 KB");
    expect(formatValue(5 * 1024 ** 3, { style: "bytes" }, L)).toBe("5 GB");
  });

  test("durations show their two largest units", () => {
    expect(formatValue(0.32, { style: "duration" }, L)).toBe("320 ms");
    expect(formatValue(45, { style: "duration" }, L)).toBe("45 s");
    expect(formatValue(192, { style: "duration" }, L)).toBe("3m 12s");
    expect(formatValue(3 * 3600 + 5 * 60 + 12, { style: "duration" }, L)).toBe("3h 5m");
    expect(formatValue(3600, { style: "duration" }, L)).toBe("1h");
  });

  test("prefix and suffix wrap the number", () => {
    expect(formatValue(212, { prefix: "p95 ", suffix: " ms" }, L)).toBe("p95 212 ms");
  });
});

describe("deltas", () => {
  test("direction and ratio", () => {
    expect(computeDelta(110, 100)).toEqual({ difference: 10, ratio: 0.1, direction: "up" });
    expect(computeDelta(90, 100)!.direction).toBe("down");
    expect(computeDelta(5, 5)!.direction).toBe("flat");
  });

  test("no ratio against zero, and none against a missing value", () => {
    expect(computeDelta(5, 0)!.ratio).toBeNull();
    expect(computeDelta(5, null)).toBeNull();
  });

  test("ratio is against the size of the previous value, so a negative base does not flip the sign", () => {
    expect(computeDelta(-50, -100)!.ratio).toBe(0.5);
  });

  test("formatting", () => {
    expect(formatDelta(computeDelta(110, 100)!, "percent", null, L)).toBe("▲ 10%");
    expect(formatDelta(computeDelta(90, 100)!, "absolute", { style: "number" }, L)).toBe("▼ 10");
    expect(formatDelta(computeDelta(5, 0)!, "percent", null, L)).toBe(`▲ ${EMPTY_VALUE}`);
    expect(formatDelta(computeDelta(0, 0)!, "percent", null, L)).toBe("0%");
  });
});

describe("thresholds", () => {
  const t = {
    base: "good",
    steps: [
      { value: 400, color: "critical" },
      { value: 250, color: "warning" },
    ],
  };

  test("each step takes over from its value upwards, whatever order they were saved in", () => {
    expect(thresholdColor(100, t)).toBe("good");
    expect(thresholdColor(250, t)).toBe("warning");
    expect(thresholdColor(399.9, t)).toBe("warning");
    expect(thresholdColor(400, t)).toBe("critical");
  });

  test("no colour for something that is not a number", () => {
    expect(thresholdColor("n/a", t)).toBeNull();
    expect(thresholdColor(null, t)).toBeNull();
  });

  test("a saved step with no usable value is dropped rather than breaking the rest", () => {
    expect(normalizeThresholds({ base: "good", steps: [{ value: "x" as any, color: "warning" }] }).steps).toEqual([]);
  });

  test("bands along a range", () => {
    expect(thresholdBands(t, 0, 500)).toEqual([
      { to: 0.5, color: "good" },
      { to: 0.8, color: "warning" },
      { to: 1, color: "critical" },
    ]);
  });

  test("steps outside the range are clamped", () => {
    // Below the range: the whole arc starts in that step's colour.
    expect(thresholdBands({ base: "good", steps: [{ value: -10, color: "warning" }] }, 0, 100)).toEqual([
      { to: 1, color: "warning" },
    ]);
    // Above it: never reached.
    expect(thresholdBands({ base: "good", steps: [{ value: 900, color: "critical" }] }, 0, 100)).toEqual([
      { to: 1, color: "good" },
    ]);
  });

  test("an empty range is one band", () => {
    expect(thresholdBands(t, 5, 5)).toEqual([{ to: 1, color: "good" }]);
  });
});

describe("mappings", () => {
  const m = [
    { value: "OK", text: "Healthy", color: "good" },
    { value: "down", text: "", color: "critical" },
  ];

  test("match ignores case and surrounding space", () => {
    expect(findMapping(" ok ", m)!.text).toBe("Healthy");
    expect(findMapping("DOWN", m)!.color).toBe("critical");
  });

  test("numbers match by their text", () => {
    expect(findMapping(0, [{ value: "0", text: "Down", color: "critical" }])!.text).toBe("Down");
  });

  test("no match, and no match for empty values", () => {
    expect(findMapping("degraded", m)).toBeNull();
    expect(findMapping(null, m)).toBeNull();
  });
});

describe("colours", () => {
  test("names resolve to the palette; anything else passes through", () => {
    expect(resolveColor("critical")).toBe("#b4342c");
    expect(resolveColor("#123456")).toBe("#123456");
    expect(resolveColor("")).toBe("#6f6b66");
  });

  test("a CSS variable on the page wins over the fallback", () => {
    document.documentElement.style.setProperty("--color-critical", "#ff0000");
    try {
      expect(resolveColor("critical")).toBe("#ff0000");
    } finally {
      document.documentElement.style.removeProperty("--color-critical");
    }
  });

  test("washes", () => {
    // The token, so the tint follows the theme the way the ink already does.
    // A tile whose background stayed pale while its text went light measured
    // 1.26:1 on the wall display.
    expect(washColor("good")).toBe("var(--color-good-wash, #e5f1ea)");
    expect(washColor("#123456")).toContain("color-mix");
    expect(washColor(null)).toBe("transparent");
  });

  test("every semantic colour offers a wash token, and its fallback", () => {
    SEMANTIC_COLOR_NAMES.forEach((name) => {
      expect(washColor(name)).toBe(`var(--color-${name}-wash, ${SEMANTIC_COLORS[name].wash})`);
    });
  });
});
