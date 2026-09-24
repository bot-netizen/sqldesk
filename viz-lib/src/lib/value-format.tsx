import React from "react";
import ReactDOMServer from "react-dom/server";
import moment from "moment/moment";
import { isString, isArray, isUndefined, isFinite, isNil, toString } from "lodash";
import { visualizationsSettings } from "@/visualizations/visualizationsSettings";
import { asValueFormat, formatValue } from "@/visualizations/shared/valueOptions";

// eslint-disable-next-line
const urlPattern =
  /(^|[\s\n]|<br\/?>)((?:https?|ftp):\/\/[\-A-Z0-9+\u0026\u2019@#\/%?=()~_|!:,.;]*[\-A-Z0-9+\u0026@#\/%=~()_|])/gi;

const hasOwnProperty = Object.prototype.hasOwnProperty;

function NullValueComponent() {
  return <span className="display-as-null">{visualizationsSettings.nullValue}</span>;
}

export function createTextFormatter(highlightLinks: any) {
  if (highlightLinks) {
    return (value: any) => {
      if (value === null) {
        return <NullValueComponent />;
      }
      if (isString(value)) {
        const Link = visualizationsSettings.LinkComponent;
        value = value.replace(urlPattern, (unused, prefix, href) => {
          const link = ReactDOMServer.renderToStaticMarkup(
            <Link href={href} target="_blank" rel="noopener noreferrer">
              {href}
            </Link>
          );
          return prefix + link;
        });
      }
      return toString(value);
    };
  }
  return (value: any) => (value === null ? <NullValueComponent /> : toString(value));
}

function toMoment(value: any) {
  if (moment.isMoment(value)) {
    return value;
  }
  if (isFinite(value)) {
    return moment(value);
  }
  // same as default `moment(value)`, but avoid fallback to `new Date()`
  return moment(toString(value), [moment.ISO_8601, moment.RFC_2822]);
}

export function createDateTimeFormatter(format: any) {
  if (isString(format) && format !== "") {
    return (value: any) => {
      if (value === null) {
        return <NullValueComponent />;
      }
      const wrapped = toMoment(value);
      return wrapped.isValid() ? wrapped.format(format) : toString(value);
    };
  }
  return (value: any) => (value === null ? <NullValueComponent /> : toString(value));
}

export function createBooleanFormatter(values: any) {
  if (isArray(values)) {
    if (values.length >= 2) {
      // Both `true` and `false` specified
      return (value: any) => {
        if (value === null) {
          return <NullValueComponent />;
        }
        if (isNil(value)) {
          return "";
        }
        return "" + values[value ? 1 : 0];
      };
    } else if (values.length === 1) {
      // Only `true`
      return (value: any) => (value ? values[0] : "");
    }
  }
  return (value: any) => {
    if (value === null) {
      return <NullValueComponent />;
    }
    if (isNil(value)) {
      return "";
    }
    return value ? "true" : "false";
  };
}

/**
 * A formatter from a saved option, which may be a numeral format string or
 * the shared `ValueFormat` the editors write now.
 *
 * The strings are read by `fromNumeral`; nothing here does its own
 * formatting any more. What is kept is this function's contract, so every
 * caller -- charts, table number columns, cohort, funnel, the maps -- is
 * unchanged: an empty cell is an empty string, or the null marker for the
 * callers that draw one.
 */
export function createNumberFormatter(format: any, canReturnHTMLElement: boolean = false) {
  const value = asValueFormat(format, null as any);
  if (value) {
    return (v: any) => {
      if (canReturnHTMLElement && v === null) {
        return <NullValueComponent />;
      }
      if (v === "" || v === null || v === undefined) {
        return "";
      }
      return formatValue(v, value);
    };
  }
  return (v: any) => (canReturnHTMLElement && v === null ? <NullValueComponent /> : toString(v));
}

export function formatSimpleTemplate(str: any, data: any) {
  if (!isString(str)) {
    return "";
  }
  return str.replace(/{{\s*([^\s]+?)\s*}}/g, (match, prop) => {
    if (hasOwnProperty.call(data, prop) && !isUndefined(data[prop])) {
      return data[prop];
    }
    return match;
  });
}
