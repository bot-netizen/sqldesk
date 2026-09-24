import { formatCounterValue } from "./utils";

/*
  The stat's classic formatting, which is the last thing numeral did in this
  application. What is pinned here is what numeral wrote for each combination
  of the boxes -- recorded from it before it was removed -- plus the one case
  where it wrote nonsense and this does not.
*/

function classic(value: any, options: Partial<Record<string, any>> = {}) {
  return formatCounterValue(value, { formatMode: "classic", stringPrefix: "", stringSuffix: "", ...options });
}

describe("a stat formatted the classic way", () => {
  test("untouched, it is the AngularJS number filter it always was", () => {
    // Three places and en delimiters, whatever the reader's locale.
    expect(classic(1234567.891)).toBe("1,234,567.891");
  });

  test.each([
    [1234567.891, { stringDecimal: 2, stringDecChar: ",", stringThouSep: " " }, "1 234 567,89"],
    [1234567.891, { stringDecimal: 3, stringDecChar: ",", stringThouSep: "." }, "1.234.567,891"],
    [1234567.891, { stringDecChar: ",", stringThouSep: " " }, "1 234 568"],
    [1234567.891, { stringThouSep: " " }, "1 234 568"],
    [0, { stringDecimal: 2, stringThouSep: "," }, "0.00"],
    [1234, { stringDecimal: 0, stringThouSep: "," }, "1,234"],
    [-1234.5, { stringDecimal: 2, stringThouSep: "," }, "-1,234.50"],
    // A negative decimal place count is not a choice, so the defaults stand.
    [1234567.891, { stringDecimal: -1 }, "1,234,567.891"],
  ])("%p with %p is %p, as numeral wrote it", (value, options, expected) => {
    expect(classic(value, options)).toBe(expected);
  });

  test("no thousands separator means none, not the word 'undefined'", () => {
    // numeral was handed the raw value and joined the groups with it:
    // "1undefined234undefined568". Anybody who cleared that box saw this.
    expect(classic(1234567.891, { stringDecimal: 2 })).toBe("1234567.89");
    expect(classic(1234567.891, { stringDecimal: 2, stringThouSep: "" })).toBe("1234567.89");
  });

  test("the prefix and suffix go round the outside", () => {
    expect(classic(1234, { stringDecimal: 0, stringThouSep: ",", stringPrefix: "$", stringSuffix: " each" })).toBe(
      "$1,234 each"
    );
  });

  test("anything that is not a number is left alone", () => {
    expect(classic("n/a", { stringDecimal: 2 })).toBe("n/a");
  });
});
