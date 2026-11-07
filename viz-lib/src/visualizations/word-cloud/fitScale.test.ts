import { fitScale, FIT_MARGIN } from "./Renderer";

/*
  The cloud was scaled to fit its box exactly, so it touched whichever edges
  limited it -- "Filters" stood on the bottom edge of its widget on the demo
  dashboard. It now fits inside a margin on every side.
*/
describe("Visualizations -> Word cloud -> fitting the box", () => {
  test("a tall cloud keeps the margin above and below", () => {
    const scale = fitScale({ width: 400, height: 600 }, { width: 698, height: 307 });
    expect(600 * scale).toBeCloseTo(307 - 2 * FIT_MARGIN, 5);
    expect(400 * scale).toBeLessThan(698 - 2 * FIT_MARGIN);
  });

  test("a wide cloud keeps the margin at the sides", () => {
    const scale = fitScale({ width: 1600, height: 300 }, { width: 698, height: 307 });
    expect(1600 * scale).toBeCloseTo(698 - 2 * FIT_MARGIN, 5);
  });

  test("an unmeasured cloud is left at its own size", () => {
    expect(fitScale({ width: 0, height: 0 }, { width: 698, height: 307 })).toBe(1);
  });
});
