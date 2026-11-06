import fs from "fs";
import path from "path";

/*
  A page's styles have to be in a stylesheet that page loads.

  Obvious, and it was true for free while everything was one bundle: any rule
  in any stylesheet reached every page. Splitting the pages into chunks ended
  that, and the first casualty was the query page, whose fixed layout -- the
  flex column that keeps the filters above the visualization -- was written in
  `components/dashboards/dashboard-grid.less`, a file only the dashboard grid
  imports. The moment the dashboard became a chunk of its own, opening a query
  drew the table over the filters. Nothing failed at build time; the only
  symptom was a Cypress click landing on the wrong element.

  So: a rule for a page may live in the always-loaded main stylesheet, or in a
  stylesheet that page's own module tree imports -- never in another page's.

  Shared declarations go in a mixin under `inc/`, which each user imports and
  gets its own copy of. Defining a mixin is not using a class, so a `()` in
  the selector is not a rule.
*/

const LESS_ROOT = path.join(__dirname, "..", "..");

function lessFiles(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      return entry.name === "node_modules" ? [] : lessFiles(full);
    }
    return entry.name.endsWith(".less") ? [full] : [];
  });
}

/** Files declaring a rule for `selector`, ignoring mixin definitions. */
function filesDeclaring(selector) {
  return lessFiles(LESS_ROOT)
    .filter((file) => {
      const source = fs.readFileSync(file, "utf8");
      return source.split("\n").some((line) => {
        const trimmed = line.trim();
        if (!trimmed.startsWith(selector)) {
          return false;
        }
        const rest = trimmed.slice(selector.length);
        // `.foo() { ... }` defines a mixin; `.foo(...)` calls one.
        return !rest.startsWith("(");
      });
    })
    .map((file) => path.relative(path.join(__dirname, "..", "..", ".."), file));
}

describe("a page's styles are in a stylesheet that page loads", () => {
  test(".query-fixed-layout is not written in another page's stylesheet", () => {
    const allowed = [
      // Always loaded: `assets/less/main.less` imports it.
      "app/assets/less/sqldesk/query.less",
      // The query pages' own, which travel in the query chunks.
      // (QueryView.less nests its rule under `&`, so it is not matched here.)
      "app/pages/queries/components/QueryVisualizationTabs.less",
    ];

    expect(filesDeclaring(".query-fixed-layout").sort()).toEqual(allowed.sort());
  });

  test("the shared fixed-box layout is a mixin, so each user gets a copy", () => {
    const mixin = fs.readFileSync(path.join(LESS_ROOT, "assets/less/inc/visualizations/fills-its-box.less"), "utf8");

    expect(mixin).toMatch(/\.visualization-fills-its-box\(\)\s*\{/);
    // A mixin definition emits nothing on its own; anything else in this file
    // would be shipped to everybody whether they needed it or not.
    expect(mixin.replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, "").trim()).toMatch(
      /^\.visualization-fills-its-box\(\)\s*\{[\s\S]*\}$/
    );
  });

  test("every file using the mixin imports it, since LESS scopes them per file", () => {
    const users = lessFiles(LESS_ROOT).filter((file) =>
      /^\s*\.visualization-fills-its-box\(\);/m.test(fs.readFileSync(file, "utf8"))
    );

    expect(users.length).toBeGreaterThan(0);

    for (const file of users) {
      const source = fs.readFileSync(file, "utf8");
      const importsIt = /@import[^;]*fills-its-box/.test(source);
      // main.less imports the mixin before the stylesheets that use it, and
      // they are compiled together, so those need no import of their own.
      const reachedThroughMain = file.includes(`${path.sep}assets${path.sep}less${path.sep}`);

      expect(importsIt || reachedThroughMain).toBe(true);
    }
  });
});

/*
  A visualization that cannot be seen in the editor.

  `.visualization-fills-its-box()` pins a container to all four edges of
  its box, and it is mixed into exactly three places: the dashboard grid,
  the query page and a notebook cell. The editor's preview is not one of
  them -- it puts the renderer in a `.scrollbox`, which has no height of
  its own -- so a pinned container with no height of its own draws at zero
  pixels there and the preview pane is blank. It looks like the
  visualization is broken; it is drawing perfectly, at nothing.

  Shipped exactly that way with parallel coordinates. Every container that
  was already in the list states a pixel height for this reason, which is
  the rule being written down here rather than invented.
*/
describe("every visualization can be seen outside a box that sizes it", () => {
  const VIZ_ROOT = path.join(LESS_ROOT, "..", "..", "viz-lib", "src", "visualizations");
  const MIXIN = path.join(LESS_ROOT, "assets/less/inc/visualizations/fills-its-box.less");

  /** The container classes `.visualization-fills-its-box()` pins. */
  function pinnedContainers() {
    const source = fs.readFileSync(MIXIN, "utf8");
    return Array.from(source.matchAll(/^\s*\.([a-z0-9-]+-visualization-container)[,{]/gm)).map((m) => m[1]);
  }

  /** What a container's own rule says, wherever viz-lib declares it. */
  function ownRule(selector) {
    for (const file of lessFiles(VIZ_ROOT)) {
      const source = fs.readFileSync(file, "utf8");
      const match = new RegExp(`^\\.${selector}\\s*\\{([^}]*)\\}`, "m").exec(source);
      if (match) {
        return match[1];
      }
    }
    return null;
  }

  test("the list is not empty, or this test proves nothing", () => {
    expect(pinnedContainers().length).toBeGreaterThan(4);
  });

  test("each pinned container also states a height for everywhere else", () => {
    const withoutFallback = pinnedContainers().filter((selector) => {
      const body = ownRule(selector);
      // Declared outside viz-lib -- not this package's to assert about.
      return body !== null && !/height:\s*\d+px/.test(body);
    });

    expect(withoutFallback).toEqual([]);
  });
});
