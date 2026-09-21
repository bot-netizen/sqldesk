import fs from "fs";
import path from "path";

/*
  The wall theme's colours, checked rather than trusted.

  A dashboard on a wall is read at four metres in a room with the lights off,
  so the margin that a light theme gets from a white background is gone. The
  light palette does not survive the move: its status green measures 2.6:1 on
  the dark surface, and two of its eight series colours land under 3:1, which
  is the floor for a graphical object let alone text.

  Worth knowing while reading this: tokens.less says its series ramp was
  "validated ... against both the light (#ffffff) and dark (#1b1a21)
  surfaces", and measured, that is not true of series 1, 5, 6 and 8 -- two of
  them land under even the 3:1 a graphical object needs. It happens not to
  matter, because nothing reads those tokens: the charts draw from
  viz-lib's own ColorPalette, whose colours do hold up here.
*/

const less = fs.readFileSync(path.join(__dirname, "tokens-wall.less"), "utf8");

function value(name) {
  const match = less.match(new RegExp(`@${name}:\\s*(#[0-9a-fA-F]{6});`));
  if (!match) {
    throw new Error(`no @${name} in tokens-wall.less`);
  }
  return match[1];
}

function channel(c) {
  const v = c / 255;
  return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
}

function luminance(hex) {
  const n = hex.replace("#", "");
  const [r, g, b] = [0, 2, 4].map((i) => channel(parseInt(n.slice(i, i + 2), 16)));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

const SURFACE = value("wall-surface");
const CANVAS = value("wall-canvas");

/** WCAG AA for normal text. */
const AA = 4.5;

describe("the wall theme's contrast", () => {
  test("the surface is the one the series ramp was drawn for", () => {
    // tokens.less names this colour; if the wall theme drifts off it the
    // series work below stops meaning anything.
    expect(SURFACE).toBe("#1b1a21");
    expect(luminance(CANVAS)).toBeLessThan(luminance(SURFACE));
  });

  describe.each([
    ["the tile", SURFACE],
    ["the page behind it", CANVAS],
  ])("against %s", (_where, background) => {
    test.each([
      ["text", "wall-text"],
      ["secondary text", "wall-text-secondary"],
      ["muted text", "wall-text-muted"],
      ["the action colour as ink", "wall-action-text"],
      ["good", "wall-good"],
      ["warning", "wall-warning"],
      ["serious", "wall-serious"],
      ["critical", "wall-critical"],
    ])("%s is readable", (_name, token) => {
      expect(contrast(value(token), background)).toBeGreaterThanOrEqual(AA);
    });
  });

  /*
    A status tile is its own surface: the wash is the background, and three
    things sit on it. The wash used to be the one part of the semantic colour
    system that read no token, so on this theme the ink followed and the
    background did not -- a pale tile under light text, 1.26:1, found by
    walking the rendered page rather than by looking at it.
  */
  describe.each([
    ["good", "wall-good-wash", "wall-good"],
    ["warning", "wall-warning-wash", "wall-warning"],
    ["serious", "wall-serious-wash", "wall-serious"],
    ["critical", "wall-critical-wash", "wall-critical"],
    ["neutral", "wall-neutral-wash", "wall-text-muted"],
    ["accent", "wall-accent-wash", "wall-action-text"],
  ])("a %s tile", (_name, washToken, inkToken) => {
    test.each([
      ["its own status ink", (t) => t.ink],
      ["the tile name, in secondary text", () => value("wall-text-secondary")],
      ["the detail line, in muted text", () => value("wall-text-muted")],
    ])("is readable under %s", (_what, pick) => {
      const wash = value(washToken);
      expect(contrast(pick({ ink: value(inkToken) }), wash)).toBeGreaterThanOrEqual(AA);
    });

    test("is a tint, not a second surface", () => {
      // Dark enough to keep light text on it, but distinguishable from the
      // plain tile beside it -- otherwise the state is carried by nothing.
      expect(luminance(value(washToken))).toBeGreaterThan(luminance(SURFACE));
      expect(luminance(value(washToken))).toBeLessThan(luminance(value("wall-text-subtle")));
    });
  });

  test("the theme does not pretend to set the chart palette", () => {
    // It cannot: viz-lib's ColorPalette.ts holds its own hardcoded hexes and
    // reads no token. Overriding --series-* here would look like a fix and do
    // nothing, so the theme does not claim to.
    expect(less).not.toMatch(/--series-\d/);
  });

  test("subtle ink is not offered as text", () => {
    // It is for dividers and disabled marks. Pinned so nobody promotes it.
    expect(contrast(value("wall-text-subtle"), SURFACE)).toBeLessThan(AA);
  });

  test("every token the theme sets has a value", () => {
    const used = [...less.matchAll(/var\(--[a-z-]+\)|@(wall-[a-z0-9-]+)/g)].map((m) => m[1]).filter(Boolean);
    [...new Set(used)].forEach((name) => expect(() => value(name)).not.toThrow());
  });
});
