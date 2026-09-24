import numeral from "numeral";
import fromNumeral, { asValueFormat } from "./fromNumeral";
import { DEFAULT_VALUE_FORMAT, formatValue } from "./format";

numeral.options.scalePercentBy100 = false;

/*
  The whole point of this file is that a chart already saved goes on looking
  the way it did. So the translation is not described here -- it is checked
  against numeral, which is what drew those charts.
*/

/** Every format string the application has ever put in a saved option. */
const SHIPPED = [
  "0,0", // table integers
  "0,0.00", // table floats, choropleth
  "0,0[.]00", // cohort, funnel
  "0,0[.]00000", // chart
  "0[.]00%", // chart, funnel
  "0.00%", // cohort
  "0,0.000", // the stat's tooltip
];

/** And a spread of what somebody might type into the same box. */
const TYPED = ["0", "0.0", "0.000", "0,0.0", "0[.]0", "0,0[.]000", "$0,0.00", "$0,0", "0.0[0]", "0%"];

/*
  No exact halves of negative numbers: numeral rounds those half *up* toward
  positive infinity (-0.5 becomes 0, -2.5 becomes -2) and Intl rounds half
  away from zero (-1, -3). Matching that would mean `roundingMode: "halfCeil"`
  on every call, which older Safari and Firefox ignore -- a number that reads
  differently depending on the browser is worse than one that differs from a
  library we are removing. There is a test for the difference below.
*/
const VALUES = [0, 1, 3, 3.5, 3.456, 12.75, -12.3456789, 1234, 1234.5678, 1000000, 0.25, -0.9234567, 99.999, 1e9];

function viaNumeral(value: number, format: string) {
  return numeral(value).format(format);
}

function viaValueFormat(value: number, format: string) {
  const translated = fromNumeral(format);
  expect(translated).not.toBeNull();
  return formatValue(value, translated as any, "en-US");
}

describe("reading a numeral format string", () => {
  describe.each([...SHIPPED, ...TYPED])("%s", (format) => {
    test.each(VALUES)("writes %p the same way numeral did", (value) => {
      expect(viaValueFormat(value, format)).toBe(viaNumeral(value, format));
    });
  });

  test("the ones it cannot read say so rather than guessing", () => {
    // A sign marker changes what a negative looks like; an ordinal and an
    // exponent are not things Intl writes. Better an unmigrated default than
    // a number that means something else.
    ["+0,0", "-0,0", "0o", "0.0e+0", "(0,0)", "", "   ", "nonsense"].forEach((format) => {
      expect(fromNumeral(format)).toBeNull();
    });
  });

  test("anything that is not a string is not a format", () => {
    [null, undefined, 0, 12, {}, []].forEach((value) => expect(fromNumeral(value)).toBeNull());
  });

  test("a percent sign is a suffix, not Intl's percent style", () => {
    // numeral is configured not to scale, so 25 formats as "25.00%". Intl's
    // percent style would make that "2,500%".
    expect(fromNumeral("0.00%")!.style).toBe("number");
    expect(fromNumeral("0.00%")!.suffix).toBe("%");
    expect(formatValue(25, fromNumeral("0.00%"), "en-US")).toBe("25.00%");
  });

  test("optional places drop their zeros, required places keep them", () => {
    expect(formatValue(3, fromNumeral("0,0[.]00"), "en-US")).toBe("3");
    expect(formatValue(3, fromNumeral("0,0.00"), "en-US")).toBe("3.00");
    // `[.]` makes the point optional, not the digits: 3.5 keeps both places.
    expect(formatValue(3.5, fromNumeral("0,0[.]00"), "en-US")).toBe("3.50");
  });

  test("a negative number keeps its sign outside the prefix", () => {
    // "$-12.75" is not how anybody writes money, and it is what concatenating
    // a prefix onto a formatted negative gives you.
    expect(formatValue(-12.75, fromNumeral("$0,0.00"), "en-US")).toBe("-$12.75");
  });

  test("an exact half of a negative number is the one thing that moved", () => {
    // numeral rounds half up toward positive infinity; Intl rounds half away
    // from zero. Everything else about these two agrees.
    expect(viaNumeral(-0.5, "0,0")).toBe("0");
    expect(formatValue(-0.5, fromNumeral("0,0"), "en-US")).toBe("-1");
    expect(viaNumeral(-2.5, "0,0")).toBe("-2");
    expect(formatValue(-2.5, fromNumeral("0,0"), "en-US")).toBe("-3");
    // Positive halves, which is the case anyone actually meets, agree.
    expect(formatValue(2.5, fromNumeral("0,0"), "en-US")).toBe(viaNumeral(2.5, "0,0"));
  });

  test("compact numbers take the locale's own letters, not numeral's", () => {
    // numeral writes "1.2k" and "1b" whatever the language; Intl writes what
    // the locale does. That is the point of moving to it.
    expect(viaNumeral(1234, "0.0a")).toBe("1.2k");
    expect(formatValue(1234, fromNumeral("0.0a"), "en-US")).toBe("1.2K");
  });

  test("bytes below one are a unit, not a blank", () => {
    // numeral writes 0.5 with "0,0 b" as "0 " -- a space where the unit
    // should be. This has never been a format anything shipped with; it is
    // here because somebody could have typed it.
    expect(viaNumeral(0.5, "0,0 b")).toBe("1 ");
    expect(formatValue(0.5, fromNumeral("0,0 b"), "en-US")).toBe("1 B");
    expect(formatValue(1234, fromNumeral("0,0 b"), "en-US")).toBe(viaNumeral(1234, "0,0 b"));
  });

  test("a number too small to show is zero, not minus zero", () => {
    // Intl signs the rounded value, so -0.1 to whole numbers came out "-0",
    // which reads as a fall to nothing. numeral has its own trouble here: it
    // drops the sign and then writes the currency marker on the wrong side,
    // "0$".
    expect(formatValue(-0.1, fromNumeral("0,0"), "en-US")).toBe("0");
    expect(formatValue(-0.1, fromNumeral("$0,0"), "en-US")).toBe("$0");
    expect(viaNumeral(-0.1, "$0,0")).toBe("0$");
  });

  test("a comma is the only thing that groups", () => {
    expect(formatValue(1234, fromNumeral("0.00"), "en-US")).toBe("1234.00");
    expect(formatValue(1234, fromNumeral("0,0.00"), "en-US")).toBe("1,234.00");
  });
});

describe("a saved option that may be either shape", () => {
  test("a string is read", () => {
    expect(asValueFormat("0,0.00").decimals).toBe(2);
  });

  test("an object passes through, filled out with the defaults", () => {
    const already = asValueFormat({ style: "currency", decimals: 2 });
    expect(already.style).toBe("currency");
    expect(already.grouping).toBe(true);
    expect(already.currency).toBe("USD");
  });

  test("running it twice changes nothing, because getOptions runs on every render", () => {
    const once = asValueFormat("0,0[.]00");
    expect(asValueFormat(once)).toEqual(once);
  });

  test("a string it cannot read falls back to what the caller offers", () => {
    const fallback = { ...DEFAULT_VALUE_FORMAT, style: "compact" as const };
    expect(asValueFormat("0.0e+0", fallback)).toBe(fallback);
    expect(asValueFormat(undefined, fallback)).toBe(fallback);
  });
});
