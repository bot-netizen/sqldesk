import { isDateTime } from "@/services/query-result";

describe("isDateTime", () => {
  it.each([
    ["2022-01-01T00:00:00", true],
    ["2022-01-01T00:00:00+09:00", true],
    ["2021-01-27T00:00:01.733983944+03:00 stderr F {", false],
    // Date-shaped but not a date: the shape test alone is not enough, so
    // moment still has to be asked about anything that gets past it.
    ["2022-13-45T00:00:00", false],
    ["2021-01-27Z00:00:00+09:00", false],
    ["2021-01-27", false],
    ["foo bar", false],
    [2022, false],
    [null, false],
    ["", false],
  ])("isDateTime('%s'). expected '%s'.", (value, expected) => {
    expect(isDateTime(value)).toBe(expected);
  });
});
