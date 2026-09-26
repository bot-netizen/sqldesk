import handleNavigationIntent from "./handleNavigationIntent";
import navigateTo from "./navigateTo";

jest.mock("./navigateTo", () => jest.fn());

/*
  The app turns every anchor click into a client-side route, which is right
  for links between pages and wrong for links to the API.

  The Catalog page's "Download YAML" link depends on the `download` escape
  hatch below. Without it the router swallowed the click, pushed
  /<org>/api/admin/catalog/export, and drew its own "page cannot be found"
  over a download that had already succeeded -- so the page reported a
  failure for something that worked.
*/
describe("handleNavigationIntent", () => {
  beforeEach(() => {
    navigateTo.mockClear();
  });

  function click(attributes) {
    const anchor = document.createElement("a");
    Object.entries(attributes).forEach(([name, value]) => anchor.setAttribute(name, value));
    document.body.appendChild(anchor);
    handleNavigationIntent({ target: anchor, preventDefault: jest.fn() });
    document.body.removeChild(anchor);
  }

  test("an ordinary link is routed inside the app", () => {
    click({ href: "/queries/1" });

    expect(navigateTo).toHaveBeenCalled();
  });

  test("a download is left to the browser", () => {
    click({ href: "/api/admin/catalog/export", download: "" });

    expect(navigateTo).not.toHaveBeenCalled();
  });

  test("so is a link opening in a new tab", () => {
    click({ href: "https://example.com", target: "_blank" });

    expect(navigateTo).not.toHaveBeenCalled();
  });

  test("and one that opts out explicitly", () => {
    click({ href: "/api/whatever", "data-skip-router": "true" });

    expect(navigateTo).not.toHaveBeenCalled();
  });
});
