import getCounterScale from "./scale";

/*
  The stat shrinks its number to fit by measuring the number and its box and
  applying a transform. Everything here is about the cases where the box
  cannot be measured: getting those wrong once made the number disappear
  rather than merely look wrong, which is much harder to notice in a test and
  much easier to notice on a wall.
*/
function box(boxWidth: number, boxHeight: number, innerWidth: number, innerHeight: number) {
  return {
    offsetWidth: boxWidth,
    offsetHeight: boxHeight,
    firstChild: { offsetWidth: innerWidth, offsetHeight: innerHeight },
  };
}

describe("getCounterScale", () => {
  test("shrinks to whichever of width and height is tighter", () => {
    expect(getCounterScale(box(200, 400, 400, 400))).toBe("0.50");
    expect(getCounterScale(box(400, 100, 400, 400))).toBe("0.25");
  });

  test("grows to fill a box bigger than the number", () => {
    expect(getCounterScale(box(800, 800, 400, 400))).toBe("2.00");
  });

  test("a box that has not been laid out yet leaves the scale alone", () => {
    // Not "0.00": that is scale(0), and the number vanishes until something
    // else happens to resize it.
    expect(getCounterScale(box(0, 0, 400, 400))).toBeNull();
    expect(getCounterScale(box(200, 0, 400, 400))).toBeNull();
    expect(getCounterScale(box(0, 200, 400, 400))).toBeNull();
  });

  test("a number that has not been drawn yet leaves the scale alone", () => {
    expect(getCounterScale(box(200, 200, 0, 0))).toBeNull();
    expect(getCounterScale({ offsetWidth: 200, offsetHeight: 200, firstChild: null })).toBeNull();
  });

  test("never returns something that would hide the number", () => {
    const cases = [box(0, 0, 0, 0), box(1, 1, 0, 400), box(-5, 200, 400, 400), box(200, 200, 400, 0)];
    cases.forEach((c) => {
      const scale = getCounterScale(c);
      expect(scale === null || Number(scale) > 0).toBe(true);
    });
  });
});
