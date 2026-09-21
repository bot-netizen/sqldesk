import fs from "fs";
import path from "path";

/*
  "My Desk" is the home page's title, and Dashboards, Queries and Alerts each
  have one in the same place. They were 18px and 30px respectively, which made
  the home page look like a caption of the others.

  The two rules live in different stylesheets, so the only thing keeping them
  the same size is this.
*/

const read = (relative) => fs.readFileSync(path.join(__dirname, relative), "utf8");

function declarations(css, selector) {
  const at = css.indexOf(selector + " {");
  if (at < 0) {
    throw new Error(`no ${selector} rule`);
  }
  const body = css.slice(at + selector.length + 2, css.indexOf("}", at));
  const found = {};
  body
    .split(";")
    .map((line) => line.trim())
    .filter(Boolean)
    .forEach((line) => {
      const [property, ...rest] = line.split(":");
      found[property.trim()] = rest.join(":").trim();
    });
  return found;
}

const homeTitle = declarations(read("./Home.less"), ".home-section-title");
const listTitle = declarations(read("../../components/items-list/components/ListPage.less"), ".list-page-heading h1");

describe("the home page's title", () => {
  test.each(["font-size", "font-weight", "letter-spacing", "line-height"])(
    "has the same %s as a list page's",
    (property) => {
      expect(homeTitle[property]).toBe(listTitle[property]);
    }
  );

  test("both were actually found", () => {
    // Guards the test: a selector that stopped matching would make every
    // check above compare undefined with undefined.
    expect(homeTitle["font-size"]).toBeTruthy();
    expect(listTitle["font-size"]).toBeTruthy();
  });
});
