import fs from "fs";
import path from "path";

/*
  The table header is marked by weight and a rule, not by a fill.

  Asserted against the stylesheet itself, which is crude and is here because
  nothing cheaper caught it. The fill was removed in two places -- the antd
  variable the whole application uses, and this file's own `th` rule -- and
  the header stayed cream anyway, because a third rule painted it:

      .table-fixed-header th { background: var(--color-surface-sunken) !important }

  The sticky header needs an opaque background, so that rule is right to set
  one. It took the *sunken* surface, which is the colour of a recess, and it
  took it with `!important`, so nothing the theme or the antd variables said
  could get past it. A rendered specimen did not show it either, because a
  specimen has nothing to scroll and so no sticky header.

  What a reader needs from a header is that it is not one of the rows. That
  comes from the weight and the rule under it; the surface it sits on is the
  same card the rows are on.
*/

const RENDERER = path.join(__dirname, "renderer.less");

function declarations(source: string, selectorPart: string): string {
  // The block a selector opens, up to its closing brace at the same depth.
  const at = source.indexOf(selectorPart);
  if (at === -1) {
    throw new Error(`${selectorPart} is no longer in renderer.less`);
  }
  const open = source.indexOf("{", at);
  let depth = 0;
  for (let i = open; i < source.length; i += 1) {
    if (source[i] === "{") depth += 1;
    if (source[i] === "}") {
      depth -= 1;
      if (depth === 0) {
        // Comments are stripped: this file explains the mistake it is
        // guarding against, and the explanation names the token.
        return source.slice(open, i).replace(/\/\/[^\n]*/g, "");
      }
    }
  }
  throw new Error("unbalanced braces in renderer.less");
}

describe("the table visualization's header surface", () => {
  const source = fs.readFileSync(RENDERER, "utf8");

  test("the sticky header is opaque, because rows scroll under it", () => {
    const sticky = declarations(source, "th:not(.table-visualization-search)");

    expect(sticky).toMatch(/background:/);
  });

  test("and it is the surface the table is on, not the sunken one", () => {
    const sticky = declarations(source, "th:not(.table-visualization-search)");

    expect(sticky).toContain("var(--color-surface)");
    expect(sticky).not.toContain("--color-surface-sunken");
  });

  test("the sticky header's colour is a token, so the wall display can move it", () => {
    // A bare literal here would be a colour no theme can reach, and with
    // `!important` on it, one no theme can override either -- which is how it
    // came to be the last white thing left on the dark wall display.
    const sticky = declarations(source, "th:not(.table-visualization-search)");
    const background = /background:([^;]*);/.exec(sticky);

    expect(background).not.toBeNull();
    expect(background![1]).toMatch(/var\(--/);
  });

  test("the header is marked by weight and a rule instead", () => {
    const header = declarations(source, ".ant-table-thead > tr > th {");

    expect(header).toMatch(/font-weight:\s*700/);
    expect(header).toMatch(/border-bottom:\s*2px/);
  });
});
