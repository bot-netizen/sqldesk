/*
  How a single value is written: the unit, the precision, and anything around
  it. Every visualization that shows one number -- a gauge, a stat, a tile, a
  table cell under a rule -- reads the same `ValueFormat`, so a value formatted
  one way in the editor looks the same wherever it lands.

  Built on Intl.NumberFormat rather than numeral. numeral has not been released
  since 2017, cannot write compact numbers ("1.2K"), and formats by mutating a
  global locale. Intl is in every browser and costs nothing to ship.

  Saved numeral format strings elsewhere (Chart's numberFormat, Table's number
  columns) are untouched; this is for the new options only.
*/

export type ValueStyle = "auto" | "number" | "compact" | "percent" | "currency" | "bytes" | "duration";

export interface ValueFormat {
  style: ValueStyle;
  /** Digits after the point. `null` lets the style decide. */
  decimals: number | null;
  /**
   * The fewest digits after the point, so trailing zeros can be dropped:
   * `null` means "as many as `decimals`", which is a fixed number of places.
   *
   * Here because numeral could say it -- `0,0[.]00` writes 3 as "3" and 3.456
   * as "3.46" -- and the formats migrated off numeral would otherwise all
   * have gained a ".00".
   */
  minDecimals: number | null;
  /**
   * A whole number is written with no decimal part at all: 3 as "3" where
   * 3.5 is "3.50". numeral wrote that `0,0[.]00` -- the *point* is optional,
   * not the digits after it -- and it is the format the charts shipped with.
   */
  hideZeroFraction: boolean;
  /** Thousands separators. Off is how a bare `0.00` was written in numeral. */
  grouping: boolean;
  prefix: string;
  suffix: string;
  /** ISO 4217 code, used by the "currency" style. */
  currency: string;
}

export const DEFAULT_VALUE_FORMAT: ValueFormat = {
  style: "auto",
  decimals: null,
  minDecimals: null,
  hideZeroFraction: false,
  grouping: true,
  prefix: "",
  suffix: "",
  currency: "USD",
};

export const VALUE_STYLES: { value: ValueStyle; label: string; example: string }[] = [
  { value: "auto", label: "Automatic", example: "1,234.5" },
  { value: "number", label: "Number", example: "1,234.50" },
  { value: "compact", label: "Compact", example: "1.2K" },
  { value: "percent", label: "Percent (0.25 is 25%)", example: "25%" },
  { value: "currency", label: "Currency", example: "$1,234.50" },
  { value: "bytes", label: "Bytes", example: "1.2 MB" },
  { value: "duration", label: "Duration (seconds)", example: "3m 12s" },
];

/** What a missing or unreadable value is shown as. */
export const EMPTY_VALUE = "–";

/*
  The separators an organization has chosen, or null to use whatever the
  reader's locale does.

  These are an organization setting -- Settings > General > Format -- and
  numeral honoured them by mutating its own global locale, which is one of
  the reasons it is going. `Intl` reads them off the locale instead, so the
  chosen ones are substituted into the parts it produces: precise, because
  the parts say which piece is a group separator and which is a decimal
  point, rather than guessing at characters in a finished string.

  Pushed in from `visualizationsSettings` rather than read from it, so this
  file goes on depending on nothing.
*/
let separators: { group: string; decimal: string } | null = null;

export function setNumberSeparators(group: unknown, decimal: unknown): void {
  // Set even when they are the ordinary "," and ".", because that is a
  // choice the organization made and it has to hold whatever locale the
  // reader's browser is in -- which is what numeral did by forcing its own
  // locale's delimiters.
  separators = typeof group === "string" && typeof decimal === "string" ? { group, decimal } : null;
}

/** Every number written by this file goes through here. */
function write(value: number, options: Intl.NumberFormatOptions, locale?: string): string {
  const formatter = new Intl.NumberFormat(locale, options);
  if (!separators) {
    return formatter.format(value);
  }
  const { group, decimal } = separators;
  return formatter
    .formatToParts(value)
    .map((part) => (part.type === "group" ? group : part.type === "decimal" ? decimal : part.value))
    .join("");
}

export function toNumber(value: unknown): number | null {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : null;
  }
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function digits(decimals: number | null, fallback: number) {
  const d = decimals === null || decimals === undefined ? fallback : Math.max(0, Math.min(20, Math.round(decimals)));
  return d;
}

/**
 * The fraction-digit part of an `Intl.NumberFormat` request.
 *
 * `minDecimals` is what lets a format say "up to two places, but do not pad":
 * unset, the two are the same and the number of places is fixed.
 */
function fixed(format: Pick<ValueFormat, "decimals" | "minDecimals" | "hideZeroFraction">, value: number) {
  const { decimals, minDecimals } = format;
  if (decimals === null || decimals === undefined) {
    return {};
  }
  const max = digits(decimals, 0);
  // "3" rather than "3.00", but "3.50" rather than "3.5": the decision is
  // about the rounded value, so 3.001 at two places is a whole number too.
  if (format.hideZeroFraction && max > 0 && Number(value.toFixed(max)) % 1 === 0) {
    return { minimumFractionDigits: 0, maximumFractionDigits: 0 };
  }
  const min = minDecimals === null || minDecimals === undefined ? max : Math.min(max, digits(minDecimals, 0));
  return { minimumFractionDigits: min, maximumFractionDigits: max };
}

const BYTE_UNITS = ["B", "KB", "MB", "GB", "TB", "PB"];

function formatBytes(value: number, decimals: number | null, locale?: string) {
  let unit = 0;
  let scaled = Math.abs(value);
  while (scaled >= 1024 && unit < BYTE_UNITS.length - 1) {
    scaled /= 1024;
    unit += 1;
  }
  const places = unit === 0 ? 0 : digits(decimals, 1);
  const body = write(scaled, { maximumFractionDigits: places }, locale);
  return `${value < 0 ? "-" : ""}${body} ${BYTE_UNITS[unit]}`;
}

function formatDuration(seconds: number, decimals: number | null, locale?: string) {
  const sign = seconds < 0 ? "-" : "";
  const s = Math.abs(seconds);
  const nf = (n: number, places: number) => write(n, { maximumFractionDigits: places }, locale);
  if (s < 1) {
    return `${sign}${nf(s * 1000, digits(decimals, 0))} ms`;
  }
  if (s < 60) {
    return `${sign}${nf(s, digits(decimals, Number.isInteger(s) ? 0 : 1))} s`;
  }
  const parts: [number, string][] = [
    [Math.floor(s / 86400), "d"],
    [Math.floor((s % 86400) / 3600), "h"],
    [Math.floor((s % 3600) / 60), "m"],
    [Math.floor(s % 60), "s"],
  ];
  // Two most significant units: "3h 5m", not "3h 5m 12s" -- a duration read at
  // a glance is a magnitude, not a timestamp.
  const first = parts.findIndex(([n]) => n > 0);
  return (
    sign +
    parts
      .slice(first, first + 2)
      .filter(([n], i) => i === 0 || n > 0)
      .map(([n, u]) => `${n}${u}`)
      .join(" ")
  );
}

function formatNumberBody(value: number, format: ValueFormat, locale?: string): string {
  const { decimals } = format;
  const useGrouping = format.grouping !== false;
  switch (format.style) {
    case "number":
      return write(
        value,
        {
          useGrouping,
          ...(decimals === null ? { maximumFractionDigits: Number.isInteger(value) ? 0 : 2 } : fixed(format, value)),
        },
        locale
      );
    case "compact":
      return write(
        value,
        { useGrouping, notation: "compact", compactDisplay: "short", maximumFractionDigits: digits(decimals, 1) },
        locale
      );
    case "percent":
      return write(value, { useGrouping, style: "percent", maximumFractionDigits: digits(decimals, 1) }, locale);
    case "currency":
      try {
        return write(
          value,
          { useGrouping, style: "currency", currency: format.currency || "USD", ...fixed(format, value) },
          locale
        );
      } catch (e) {
        // An unknown currency code throws; fall back rather than blank the tile.
        return write(value, { useGrouping, ...fixed(format, value) }, locale);
      }
    case "bytes":
      return formatBytes(value, decimals, locale);
    case "duration":
      return formatDuration(value, decimals, locale);
    case "auto":
    default:
      return write(
        value,
        {
          useGrouping,
          maximumFractionDigits:
            decimals === null ? (Number.isInteger(value) ? 0 : Math.abs(value) >= 100 ? 1 : 2) : digits(decimals, 0),
          ...(decimals === null ? {} : fixed(format, value)),
        },
        locale
      );
  }
}

export function normalizeValueFormat(format?: Partial<ValueFormat> | null): ValueFormat {
  return { ...DEFAULT_VALUE_FORMAT, ...(format || {}) };
}

/**
 * Write `value` as `format` says. Text passes through untouched -- a status
 * column saying "Down" should not grow a currency sign.
 */
export function formatValue(value: unknown, format?: Partial<ValueFormat> | null, locale?: string): string {
  if (value === null || value === undefined || value === "") {
    return EMPTY_VALUE;
  }
  const f = normalizeValueFormat(format);
  const n = toNumber(value);
  if (n === null) {
    return typeof value === "string" ? value : String(value);
  }
  const body = formatNumberBody(n, f, locale);
  // A number too small to show is zero, not minus zero. Rounding -0.1 to
  // whole numbers gave "-0", which reads as a fall to nothing.
  if (n < 0 && !/[1-9]/.test(body)) {
    return `${f.prefix}${formatNumberBody(Math.abs(n), f, locale)}${f.suffix}`;
  }
  // The minus goes outside the prefix. Concatenating the two gave "$-12.75",
  // which is not how anybody writes money -- and every style that carries a
  // unit, bytes and durations included, has the same problem.
  if (f.prefix && n < 0) {
    return `-${f.prefix}${formatNumberBody(Math.abs(n), f, locale)}${f.suffix}`;
  }
  return `${f.prefix}${body}${f.suffix}`;
}

export type DeltaMode = "percent" | "absolute";

export interface Delta {
  /** `current - previous`. */
  difference: number;
  /** `difference / |previous|`, or null when there is nothing to divide by. */
  ratio: number | null;
  direction: "up" | "down" | "flat";
}

export function computeDelta(current: unknown, previous: unknown): Delta | null {
  const c = toNumber(current);
  const p = toNumber(previous);
  if (c === null || p === null) {
    return null;
  }
  const difference = c - p;
  return {
    difference,
    ratio: p === 0 ? null : difference / Math.abs(p),
    direction: difference > 0 ? "up" : difference < 0 ? "down" : "flat",
  };
}

/** "▲ 4.2%", "▼ 1,203", "0%". Arrows carry the direction so colour does not have to. */
export function formatDelta(
  delta: Delta,
  mode: DeltaMode,
  format?: Partial<ValueFormat> | null,
  locale?: string
): string {
  const arrow = delta.direction === "up" ? "▲ " : delta.direction === "down" ? "▼ " : "";
  if (mode === "percent") {
    if (delta.ratio === null) {
      return delta.direction === "flat" ? "0%" : `${arrow}${EMPTY_VALUE}`;
    }
    return `${arrow}${new Intl.NumberFormat(locale, { style: "percent", maximumFractionDigits: 1 }).format(
      Math.abs(delta.ratio)
    )}`;
  }
  const f = normalizeValueFormat(format);
  return `${arrow}${f.prefix}${formatNumberBody(Math.abs(delta.difference), f, locale)}${f.suffix}`;
}
