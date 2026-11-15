import fs from "fs";
import path from "path";

/*
  An embed is somebody else's page.

  A dashboard put in a customer's portal, or a chart in a wiki, should look
  like it belongs there -- not carry a "Powered by" footer and a logo for a
  tool the reader has never heard of and cannot sign in to. The product name
  belongs in the product.

  Read off the source rather than rendered, because what matters is that
  nobody adds it back: a snapshot of the current markup would be updated
  along with the change that reintroduced it.
*/
const PAGES = {
  "the public dashboard": path.join(__dirname, "PublicDashboardPage.jsx"),
  "the embedded visualization": path.join(__dirname, "..", "queries", "VisualizationEmbed.jsx"),
};

describe("what an embed says about the tool that drew it", () => {
  Object.entries(PAGES).forEach(([what, file]) => {
    const source = fs.readFileSync(file, "utf8");

    test(`${what} carries no logo`, () => {
      expect(source).not.toContain("sqldesk_icon.svg");
    });

    test(`${what} does not name the product`, () => {
      // Import lines are excluded: `@sqldesk/viz` is a package name, which
      // nobody reading an embed ever sees. What matters is the markup.
      const shown = source
        .split("\n")
        .filter((line) => !/^\s*import\b/.test(line))
        .join("\n");

      expect(shown.toLowerCase()).not.toContain("sqldesk");
    });

    test(`${what} does not link anywhere promotional`, () => {
      expect(source).not.toContain("Powered by");
    });
  });
});
