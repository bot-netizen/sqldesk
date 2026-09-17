import MockDate from "mockdate";

const date = new Date("2000-01-01T02:00:00.000");

MockDate.set(date);

// jsdom implements no media queries at all, and antd asks for them the moment
// anything responsive renders -- Table, Grid, Drawer -- which fails the test
// with "window.matchMedia is not a function" rather than anything about the
// component under test.
//
// Everything reports as not matching. A test that needs a query to match should
// override this itself; making one up here would silently put every other test
// in some particular viewport.
if (typeof window !== "undefined" && !window.matchMedia) {
  window.matchMedia = (query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {}, // removed from the standard, still called by older libs
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  });
}
