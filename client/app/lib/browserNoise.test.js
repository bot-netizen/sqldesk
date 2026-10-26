import isBenignBrowserNoise from "./browserNoise";

/*
  The case that matters is the one with no `error` object: that is how
  ResizeObserver's warning actually arrives, and why it used to reach the
  report.
*/
describe("isBenignBrowserNoise", () => {
  test.each([
    [
      "Chrome's wording, as a bare message",
      { message: "ResizeObserver loop completed with undelivered notifications." },
    ],
    ["Safari's wording", { message: "ResizeObserver loop limit exceeded" }],
    [
      "the same thing wrapped in an Error",
      { error: new Error("ResizeObserver loop limit exceeded"), message: "Uncaught Error" },
    ],
    [
      "a message the browser prefixed",
      { message: "Uncaught Error: ResizeObserver loop completed with undelivered notifications." },
    ],
  ])("suppresses %s", (_what, event) => {
    expect(isBenignBrowserNoise(event)).toBe(true);
  });

  test.each([
    ["a programming error", { error: new TypeError("x is not a function"), message: "Uncaught TypeError" }],
    ["a failed request", { error: new Error("Request failed with status code 500") }],
    ["a chunk that went missing", { error: new Error("Loading CSS chunk 4373 failed") }],
    ["an error that merely mentions resizing", { error: new Error("ResizeObserver is not defined") }],
    ["an empty event", {}],
    ["nothing at all", null],
  ])("lets %s through", (_what, event) => {
    expect(isBenignBrowserNoise(event)).toBe(false);
  });
});
