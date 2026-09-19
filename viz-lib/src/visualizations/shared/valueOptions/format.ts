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
  prefix: string;
  suffix: string;
  /** ISO 4217 code, used by the "currency" style. */
  currency: string;
}

export const DEFAULT_VALUE_FORMAT: ValueFormat = {
  style: "auto",
  decimals: null,
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

function fixed(decimals: number | null) {
  return decimals === null || decimals === undefined
    ? {}
    : { minimumFractionDigits: digits(decimals, 0), maximumFractionDigits: digits(decimals, 0) };
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
  const body = new Intl.NumberFormat(locale, { maximumFractionDigits: places }).format(scaled);
  return `${value < 0 ? "-" : ""}${body} ${BYTE_UNITS[unit]}`;
}

function formatDuration(seconds: number, decimals: number | null, locale?: string) {
  const sign = seconds < 0 ? "-" : "";
  const s = Math.abs(seconds);
  const nf = (n: number, places: number) => new Intl.NumberFormat(locale, { maximumFractionDigits: places }).format(n);
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
  switch (format.style) {
    case "number":
      return new Intl.NumberFormat(locale, {
        ...(decimals === null ? { maximumFractionDigits: Number.isInteger(value) ? 0 : 2 } : fixed(decimals)),
      }).format(value);
    case "compact":
      return new Intl.NumberFormat(locale, {
        notation: "compact",
        compactDisplay: "short",
        maximumFractionDigits: digits(decimals, 1),
      }).format(value);
    case "percent":
      return new Intl.NumberFormat(locale, { style: "percent", maximumFractionDigits: digits(decimals, 1) }).format(
        value
      );
    case "currency":
      try {
        return new Intl.NumberFormat(locale, {
          style: "currency",
          currency: format.currency || "USD",
          ...fixed(decimals),
        }).format(value);
      } catch (e) {
        // An unknown currency code throws; fall back rather than blank the tile.
        return new Intl.NumberFormat(locale, fixed(decimals)).format(value);
      }
    case "bytes":
      return formatBytes(value, decimals, locale);
    case "duration":
      return formatDuration(value, decimals, locale);
    case "auto":
    default:
      return new Intl.NumberFormat(locale, {
        maximumFractionDigits:
          decimals === null ? (Number.isInteger(value) ? 0 : Math.abs(value) >= 100 ? 1 : 2) : digits(decimals, 0),
        ...(decimals === null ? {} : { minimumFractionDigits: digits(decimals, 0) }),
      }).format(value);
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
  return `${f.prefix}${formatNumberBody(n, f, locale)}${f.suffix}`;
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
