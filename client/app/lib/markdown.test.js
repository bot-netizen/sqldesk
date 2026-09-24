import toHtml from "./markdown";

/*
  What this replaced -- `markdown@0.5.0`, last released 2013 -- refused most
  of what anybody writing a section on a dashboard would type. Each of those
  refusals is a test here, because the point of the swap was to end them.
*/

describe("markdown a dashboard author writes", () => {
  test("a table is a table, not a paragraph of pipes", () => {
    const html = toHtml("| region | revenue |\n|---|---|\n| North | 4120 |");

    expect(html).toContain("<table>");
    expect(html).toContain("<th>region</th>");
    expect(html).toContain("<td>North</td>");
    expect(html).not.toContain("|---|");
  });

  test("a fenced block keeps its newlines and says what language it is", () => {
    const html = toHtml("```sql\nselect 1\nfrom t\n```");

    expect(html).toContain('<code class="language-sql">');
    expect(html).toContain("select 1\nfrom t");
  });

  test("strikethrough, task lists and bare URLs all work", () => {
    expect(toHtml("~~gone~~")).toContain("<del>gone</del>");
    expect(toHtml("- [x] done")).toContain('type="checkbox"');
    expect(toHtml("see https://example.com now")).toContain('<a href="https://example.com">');
  });

  test("a single newline is a line break", () => {
    // CommonMark says it is not, and the old library agreed -- but nobody
    // typing into a box five rows tall means "join these into a paragraph".
    expect(toHtml("line one\nline two")).toContain("<br>");
  });

  test("raw HTML passes through, for the sections plain markdown cannot write", () => {
    const html = toHtml('<div style="display:flex;gap:16px"><b>two</b><b>columns</b></div>');

    expect(html).toContain("<div");
    expect(html).toContain("display:flex");
    expect(html).not.toContain("&lt;div");
  });

  test("the ordinary things still work", () => {
    expect(toHtml("## Title")).toContain("<h2>Title</h2>");
    expect(toHtml("**bold** and *italic*")).toContain("<strong>bold</strong>");
    expect(toHtml("- one\n- two")).toContain("<li>one</li>");
    expect(toHtml("> quoted")).toContain("<blockquote>");
    expect(toHtml("[text](https://example.com)")).toContain('href="https://example.com"');
  });

  test("nothing at all is nothing, not a crash", () => {
    [null, undefined, "", 0].forEach((value) => expect(typeof toHtml(value)).toBe("string"));
  });
});

describe("what keeps raw HTML safe", () => {
  // This file renders HTML; it does not sanitise. `HtmlContent` runs
  // DOMPurify over every string before it reaches the DOM, which is the only
  // reason passing raw HTML through here is allowed.
  // eslint-disable-next-line global-require
  const sanitize = require("@sqldesk/viz/lib/services/sanitize").default;

  test("a script in a textbox never reaches the page", () => {
    expect(sanitize(toHtml("<script>alert(1)</script>"))).not.toContain("script");
  });

  test("nor an event handler on something that looks harmless", () => {
    const html = sanitize(toHtml('<img src="x" onerror="alert(1)">'));
    expect(html).not.toContain("onerror");
  });

  test("but the layout an author actually wanted survives", () => {
    const html = sanitize(toHtml('<div style="display:flex;gap:16px"><span>a</span><span>b</span></div>'));
    expect(html).toContain("display:flex");
    expect(html).toContain("<span>a</span>");
  });
});
