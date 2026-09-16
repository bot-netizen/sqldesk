import { easeOut, interpolate } from "./useCountUp";
import { formatCounterValue, getCounterData } from "./utils";

describe("Visualizations -> Counter -> count up", () => {
  describe("interpolation", () => {
    test("starts at the old value and ends at the new one", () => {
      expect(interpolate(2, 4, 0)).toBe(2);
      expect(interpolate(2, 4, 1)).toBe(4);
    });

    test("eases out, so it decelerates into the final value", () => {
      const halfway = interpolate(0, 100, 0.5);
      expect(halfway).toBeGreaterThan(50);
      expect(halfway).toBeLessThan(100);
    });

    test("clamps values outside the transition", () => {
      expect(interpolate(2, 4, -1)).toBe(2);
      expect(interpolate(2, 4, 2)).toBe(4);
    });

    test("counts downwards too", () => {
      expect(interpolate(10, 4, 1)).toBe(4);
      expect(interpolate(10, 4, 0.5)).toBeLessThan(10);
    });

    test("easing stays within bounds", () => {
      expect(easeOut(0)).toBe(0);
      expect(easeOut(1)).toBe(1);
    });
  });

  describe("the raw value the animation needs", () => {
    test("getCounterData exposes the number as well as the formatted string", () => {
      const rows = [{ total: 1234 }];
      const result: any = getCounterData(rows, { counterColName: "total" }, "Total");

      expect(result.counterValueRaw).toBe(1234);
      // The formatted string is unchanged for every existing caller.
      expect(typeof result.counterValue).toBe("string");
    });

    test("a non-numeric counter has no raw value, so it never animates", () => {
      const rows = [{ label: "n/a" }];
      const result: any = getCounterData(rows, { counterColName: "label" }, "Label");

      expect(result.counterValueRaw).toBeNull();
    });

    test("intermediate frames are formatted exactly like the final value", () => {
      const options = { stringPrefix: "$", stringDecimal: 0 };

      expect(formatCounterValue(interpolate(2, 4, 1), options)).toBe(formatCounterValue(4, options));
      expect(formatCounterValue(3, options)).toMatch(/^\$/);
    });
  });
});
