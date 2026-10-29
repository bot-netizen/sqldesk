import isMissingLogo from "./logoAssets";

/*
  The listing is passed in here. In the browser it comes from webpack; under
  jest `require.context` does not exist, so the module's own listing is null --
  which is the "know nothing, ask anyway" case pinned at the bottom.
*/
const known = new Set(["db-logos/pg.png", "db-logos/mysql.png", "destinations/slack.png", "avatar.svg"]);

describe("isMissingLogo", () => {
  test.each([
    ["a data source type with no file", "/static/images/db-logos/mimir.png"],
    ["a destination type with no file", "static/images/destinations/pagerduty.png"],
    ["a full URL", "https://sqldesk.example.com/static/images/db-logos/mimir.png"],
  ])("spots %s", (_what, src) => {
    expect(isMissingLogo(src, known)).toBe(true);
  });

  test.each([
    ["a logo that is there", "/static/images/db-logos/pg.png"],
    ["a destination logo that is there", "static/images/destinations/slack.png"],
    ["something outside the image folder", "/static/other/thing.png"],
    ["an absent source", null],
  ])("leaves %s alone", (_what, src) => {
    expect(isMissingLogo(src, known)).toBe(false);
  });

  test("claims nothing when the build cannot say what exists", () => {
    // Better a 404 than a tile covering a logo that is really there.
    expect(isMissingLogo("/static/images/db-logos/mimir.png", null)).toBe(false);
  });
});
