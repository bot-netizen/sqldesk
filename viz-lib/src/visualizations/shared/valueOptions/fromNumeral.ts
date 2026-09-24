import { DEFAULT_VALUE_FORMAT, ValueFormat, ValueStyle } from "./format";

/*
  Reading a numeral format string as a `ValueFormat`.

  Two number-formatting stacks shipped side by side: numeral format strings
  for charts, table number columns, cohort, funnel and the maps, and
  `ValueFormat` for the stat, gauge, progress and status grid. The same number
  could be written two ways in two widgets on one dashboard, and numeral --
  unreleased since 2017 -- formats by mutating a global locale, which
  `counter/utils.ts` had to save and restore around every call.

  So the strings are read once, here, and stored as the shared format. What
  this has to get right is that a chart already saved goes on looking the way
  it did, which is why `fromNumeral.test.ts` checks the result against numeral
  itself over every format string the application has ever offered.

  Note `%`: numeral is configured with `scalePercentBy100 = false`, so
  `numeral(25).format("0.00%")` is "25.00%" -- it appends a sign and does not
  multiply. That is a suffix, not `Intl`'s percent style, which would divide
  every cohort percentage by a hundred.
*/

const SHAPE = /^([+-]?)(\$?)(0|0(?:,0+)*)(?:(\[\.\]|\.)((?:0+|\[0+\])+))?\s?(%|a|o|b|ib|bd)?$/;

/** How many places the digits after the point ask for, required and optional. */
function places(digits: string): { max: number; min: number } {
  let min = 0;
  let max = 0;
  let optional = false;
  for (let i = 0; i < digits.length; i += 1) {
    if (digits[i] === "[") {
      optional = true;
    } else if (digits[i] === "]") {
      optional = false;
    } else if (digits[i] === "0") {
      max += 1;
      if (!optional) {
        min += 1;
      }
    }
  }
  return { max, min };
}

const UNIT_STYLE: Record<string, ValueStyle> = { a: "compact", b: "bytes", ib: "bytes", bd: "bytes" };

/**
 * A numeral format string as a `ValueFormat`, or null when it says something
 * this cannot -- an ordinal, an exponent, a bracketed negative.
 *
 * A null is not a failure to be logged: it means "leave the default alone",
 * which is what a caller migrating a saved option should do.
 */
export default function fromNumeral(format: unknown): ValueFormat | null {
  if (typeof format !== "string" || format.trim() === "") {
    return null;
  }
  const parts = SHAPE.exec(format.trim());
  if (!parts) {
    return null;
  }
  const [, sign, currency, integer, point, digits, unit] = parts;

  // The sign markers change what a negative looks like, not the number, and
  // Intl has no equivalent. Rather than write "+" into a prefix and have it
  // appear on negatives too, this declines to read the string.
  if (sign) {
    return null;
  }
  if (unit === "o") {
    return null;
  }

  const fraction = digits ? places(digits) : { max: 0, min: 0 };
  const optionalPoint = point === "[.]";

  return {
    ...DEFAULT_VALUE_FORMAT,
    style: unit && UNIT_STYLE[unit] ? UNIT_STYLE[unit] : "number",
    grouping: integer.includes(","),
    decimals: fraction.max,
    minDecimals: fraction.min,
    // `[.]00` makes the *point* optional, not the digits after it: a whole
    // number loses the fraction entirely, and anything else keeps both places.
    hideZeroFraction: optionalPoint,
    prefix: currency ? "$" : "",
    suffix: unit === "%" ? "%" : "",
  };
}

/**
 * A saved option that may be either shape, as a `ValueFormat`.
 *
 * Idempotent, because `getOptions` runs on every render: an option already
 * migrated is an object and passes straight through.
 */
export function asValueFormat(saved: unknown, fallback: ValueFormat = DEFAULT_VALUE_FORMAT): ValueFormat {
  if (saved && typeof saved === "object") {
    return { ...DEFAULT_VALUE_FORMAT, ...(saved as Partial<ValueFormat>) };
  }
  return fromNumeral(saved) || fallback;
}
