import fs from "fs";
import path from "path";

/*
  viz-lib carries its own copy of the status colours, as fallbacks for when it
  draws somewhere the tokens are not defined -- server rendering, tests,
  embeds. Two copies of a colour drift, and the drift is invisible: the
  fallback only shows up where nobody is looking.

  So the copies are checked against each other here rather than trusted. This
  file is the source; colors.ts says so in a comment, which is not enforcement.
*/

const here = path.join(__dirname);
const tokens = fs.readFileSync(path.join(here, "tokens.less"), "utf8");
const colors = fs.readFileSync(
  path.join(here, "../../../../../viz-lib/src/visualizations/shared/valueOptions/colors.ts"),
  "utf8"
);

function lessValue(name) {
  const match = tokens.match(new RegExp(`@${name}:\\s*(#[0-9a-fA-F]{6});`));
  if (!match) {
    throw new Error(`no @${name} in tokens.less`);
  }
  return match[1];
}

/** Every swatch in colors.ts, as { name, cssVar, fallback, washVar, wash }. */
function swatches() {
  const body = colors.slice(colors.indexOf("SEMANTIC_COLORS"), colors.indexOf("SEMANTIC_COLOR_NAMES"));
  const found = {};
  // Each swatch is an object literal keyed by the colour name; the fields may
  // be on one line or wrapped, so they are read individually.
  [...body.matchAll(/(\w+):\s*\{([^}]*)\}/g)].forEach(([, name, fields]) => {
    const field = (key) => {
      const m = fields.match(new RegExp(`${key}:\\s*"([^"]*)"`));
      return m ? m[1] : undefined;
    };
    found[name] = {
      cssVar: field("cssVar"),
      fallback: field("fallback"),
      washVar: field("washVar"),
      wash: field("wash"),
    };
  });
  return found;
}

const SWATCHES = swatches();

describe("the colours viz-lib keeps a copy of", () => {
  test("there are six of them, and the file was actually parsed", () => {
    // Guards the test itself: a parse that silently found nothing would make
    // every check below pass without comparing anything.
    expect(Object.keys(SWATCHES).sort()).toEqual(["accent", "critical", "good", "neutral", "serious", "warning"]);
  });

  test.each([
    ["good", "status-good", "wash-good"],
    ["warning", "status-warning", "wash-warning"],
    ["serious", "status-serious", "wash-serious"],
    ["critical", "status-critical", "wash-critical"],
  ])("%s matches the token it falls back from", (name, inkToken, washToken) => {
    expect(SWATCHES[name].fallback).toBe(lessValue(inkToken));
    expect(SWATCHES[name].wash).toBe(lessValue(washToken));
  });

  test.each([
    ["neutral", "wash-neutral"],
    ["accent", "wash-accent"],
  ])("%s's wash matches its token", (name, washToken) => {
    // Their ink comes from the text and action ramps rather than the status
    // ones, so only the wash is paired here.
    expect(SWATCHES[name].wash).toBe(lessValue(washToken));
  });

  test("every swatch names a wash token, and the app defines it", () => {
    Object.entries(SWATCHES).forEach(([name, swatch]) => {
      expect(swatch.washVar).toBe(`--color-${name}-wash`);
      expect(tokens_root()).toContain(swatch.washVar);
    });
  });
});

function tokens_root() {
  return fs.readFileSync(path.join(here, "tokens-root.less"), "utf8");
}
