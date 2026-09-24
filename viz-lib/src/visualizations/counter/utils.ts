import { isNumber, isFinite, toString } from "lodash";
import { formatValue as formatStandard } from "../shared/valueOptions";
import { createNumberFormatter } from "@/lib/value-format";
import { pickRow } from "../shared/rows";

/*
  The stat's classic formatting: a number of decimal places and a pair of
  separators chosen on the visualization itself.

  Written out by hand rather than handed to a formatter. Nothing else in the
  application lets a single visualization choose its own separators -- the
  organization chooses them, once, in Settings -- and this exists only so
  that a counter saved before the shared format keeps the look it had.

  It used to work by mutating numeral's global locale and putting it back
  afterwards, which is the last reason numeral was still here, and which had
  a bug in it: handed no thousands separator, numeral wrote the string
  "undefined" between every group. "1undefined234undefined568". Empty now
  means what anyone would expect it to mean -- no separator.
*/
function numberFormat(value: any, decimalPoints: any, decimalDelimiter: any, thousandsDelimiter: any) {
  // AngularJS's `number` filter defaults, which is how this looked before
  // anybody touched the boxes.
  let places = 3;
  let thousands = ",";
  let decimal = ".";

  const chosen = (Number.isFinite(decimalPoints) && decimalPoints >= 0) || decimalDelimiter || thousandsDelimiter;
  if (chosen) {
    places = Number.isFinite(decimalPoints) && decimalPoints > 0 ? Math.min(20, Math.round(decimalPoints)) : 0;
    decimal = decimalDelimiter || ".";
    thousands = typeof thousandsDelimiter === "string" ? thousandsDelimiter : "";
  }

  const rounded = Math.abs(Number(value)).toFixed(places);
  const [whole, fraction] = rounded.split(".");
  const grouped = thousands ? whole.replace(/\B(?=(\d{3})+(?!\d))/g, thousands) : whole;
  const negative = Number(value) < 0 && Number(rounded) !== 0;
  return `${negative ? "-" : ""}${grouped}${fraction ? decimal + fraction : ""}`;
}

function formatValue(value: any, options: any) {
  // "value" is the shared format (units, compact, currency). Counters saved
  // before it existed have no formatMode and keep the classic delimiters.
  if (options && options.formatMode === "value") {
    return formatStandard(value, options.valueFormat);
  }
  return formatClassic(value, options);
}

function formatClassic(value: any, { stringPrefix, stringSuffix, stringDecimal, stringDecChar, stringThouSep }: any) {
  if (isNumber(value)) {
    value = numberFormat(value, stringDecimal, stringDecChar, stringThouSep);
    return toString(stringPrefix) + value + toString(stringSuffix);
  }
  return toString(value);
}

/** What numeral wrote when asked for no particular format. */
const NUMERAL_DEFAULT_FORMAT = "0,0";

function formatTooltip(value: any, formatString: any) {
  if (isNumber(value)) {
    return createNumberFormatter(formatString || NUMERAL_DEFAULT_FORMAT)(value);
  }
  return toString(value);
}

/** Format a counter value exactly as the renderer displays it. */
export function formatCounterValue(value: any, options: any) {
  return formatValue(value, options);
}

export function getCounterData(rows: any, options: any, visualizationName: any) {
  const result = {};
  const rowsCount = rows.length;

  if (rowsCount > 0 || options.countRow) {
    const counterColName = options.counterColName;
    const targetColName = options.targetColName;

    // @ts-expect-error ts-migrate(2339) FIXME: Property 'counterLabel' does not exist on type '{}... Remove this comment to see the full error message
    result.counterLabel = options.counterLabel || visualizationName;

    if (options.countRow) {
      // @ts-expect-error ts-migrate(2339) FIXME: Property 'counterValue' does not exist on type '{}... Remove this comment to see the full error message
      result.counterValue = rowsCount;
    } else if (counterColName) {
      const row = pickRow<any>(rows, options.rowNumber);
      // @ts-expect-error ts-migrate(2339) FIXME: Property 'counterValue' does not exist on type '{}... Remove this comment to see the full error message
      result.counterValue = row ? row[counterColName] : undefined;
    }

    // @ts-expect-error ts-migrate(2339) FIXME: Property 'showTrend' does not exist on type '{}'.
    result.showTrend = false;

    if (targetColName) {
      // `countRow` lets this be reached with no rows at all, where reading
      // the row straight out of the array threw.
      const targetRow = pickRow<any>(rows, options.targetRowNumber);
      // @ts-expect-error ts-migrate(2339) FIXME: Property 'targetValue' does not exist on type '{}'... Remove this comment to see the full error message
      // No row to read means no target, the same as no target column at all.
      result.targetValue = targetRow ? targetRow[targetColName] : null;

      // @ts-expect-error ts-migrate(2339) FIXME: Property 'counterValue' does not exist on type '{}... Remove this comment to see the full error message
      if (Number.isFinite(result.counterValue) && isFinite(result.targetValue)) {
        // @ts-expect-error ts-migrate(2339) FIXME: Property 'counterValue' does not exist on type '{}... Remove this comment to see the full error message
        const delta = result.counterValue - result.targetValue;
        // @ts-expect-error ts-migrate(2339) FIXME: Property 'showTrend' does not exist on type '{}'.
        result.showTrend = true;
        // @ts-expect-error ts-migrate(2339) FIXME: Property 'trendPositive' does not exist on type '{... Remove this comment to see the full error message
        result.trendPositive = delta >= 0;
      }
    } else {
      // @ts-expect-error ts-migrate(2339) FIXME: Property 'targetValue' does not exist on type '{}'... Remove this comment to see the full error message
      result.targetValue = null;
    }

    // @ts-expect-error ts-migrate(2339) FIXME: Property 'counterValueTooltip' does not exist on t... Remove this comment to see the full error message
    result.counterValueTooltip = formatTooltip(result.counterValue, options.tooltipFormat);
    // @ts-expect-error ts-migrate(2339) FIXME: Property 'targetValueTooltip' does not exist on ty... Remove this comment to see the full error message
    result.targetValueTooltip = formatTooltip(result.targetValue, options.tooltipFormat);

    // The unformatted number, for callers that need to animate between values.
    // Everything below this point turns it into a display string.
    // @ts-expect-error ts-migrate(2339) FIXME: Property 'counterValueRaw' does not exist on type '{}'
    result.counterValueRaw = isNumber(result.counterValue) ? result.counterValue : null;

    // @ts-expect-error ts-migrate(2339) FIXME: Property 'counterValue' does not exist on type '{}... Remove this comment to see the full error message
    result.counterValue = formatValue(result.counterValue, options);

    if (options.formatTargetValue) {
      // @ts-expect-error ts-migrate(2339) FIXME: Property 'targetValue' does not exist on type '{}'... Remove this comment to see the full error message
      result.targetValue = formatValue(result.targetValue, options);
    } else {
      // @ts-expect-error ts-migrate(2339) FIXME: Property 'targetValue' does not exist on type '{}'... Remove this comment to see the full error message
      if (isFinite(result.targetValue)) {
        // @ts-expect-error ts-migrate(2339) FIXME: Property 'targetValue' does not exist on type '{}'... Remove this comment to see the full error message
        result.targetValue = createNumberFormatter("0[.]00[0]")(result.targetValue);
      }
    }
  }

  return result;
}

export function isValueNumber(rows: any, options: any) {
  if (options.countRow) {
    return true; // array length is always a number
  }

  const rowsCount = rows.length;
  if (rowsCount > 0) {
    const row = pickRow<any>(rows, options.rowNumber);
    const counterColName = options.counterColName;
    if (counterColName) {
      return !!row && isNumber(row[counterColName]);
    }
  }

  return false;
}
