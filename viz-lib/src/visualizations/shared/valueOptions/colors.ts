/*
  Colours a visualization picks for a value -- by threshold, by mapping, or by
  status -- are stored by *meaning* ("critical"), not by hex. The same saved
  option then follows the application's theme, and a threshold set to
  "warning" stays the warning colour if the palette is ever retuned.

  A saved colour can still be any CSS colour; names that are not ours pass
  through as they are.
*/

export type SemanticColor = "good" | "warning" | "serious" | "critical" | "neutral" | "accent";

interface Swatch {
  label: string;
  /** The application token, when the page defines one. */
  cssVar: string;
  /** Used when the token is missing -- server rendering, tests, embeds. */
  fallback: string;
  /** The token for a tint of it: a tile's background, a table cell's. */
  washVar: string;
  /** Used when that token is missing, same as `fallback`. */
  wash: string;
}

// Values from client/app/assets/less/inc/tokens.less.
export const SEMANTIC_COLORS: Record<SemanticColor, Swatch> = {
  good: { label: "Good", cssVar: "--color-good", fallback: "#1e7a4c", washVar: "--color-good-wash", wash: "#e5f1ea" },
  warning: {
    label: "Warning",
    cssVar: "--color-warning",
    fallback: "#9a6510",
    washVar: "--color-warning-wash",
    wash: "#f7eedd",
  },
  serious: {
    label: "Serious",
    cssVar: "--color-serious",
    fallback: "#c2560e",
    washVar: "--color-serious-wash",
    wash: "#fbeadf",
  },
  critical: {
    label: "Critical",
    cssVar: "--color-critical",
    fallback: "#b4342c",
    washVar: "--color-critical-wash",
    wash: "#f8e5e3",
  },
  neutral: {
    label: "Neutral",
    cssVar: "--color-text-muted",
    fallback: "#6f6b66",
    washVar: "--color-neutral-wash",
    wash: "#f1efec",
  },
  accent: {
    label: "Accent",
    cssVar: "--color-action",
    fallback: "#0a7c93",
    washVar: "--color-accent-wash",
    wash: "#e4f4f7",
  },
};

export const SEMANTIC_COLOR_NAMES = Object.keys(SEMANTIC_COLORS) as SemanticColor[];

export function isSemanticColor(name: unknown): name is SemanticColor {
  return typeof name === "string" && Object.prototype.hasOwnProperty.call(SEMANTIC_COLORS, name);
}

function readCssVar(name: string): string {
  if (typeof window === "undefined" || typeof document === "undefined" || !window.getComputedStyle) {
    return "";
  }
  return window.getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/** A concrete colour for canvas drawing, which cannot read CSS variables. */
export function resolveColor(name: string | null | undefined, fallback: SemanticColor = "neutral"): string {
  if (!name) {
    return resolveColor(fallback);
  }
  if (isSemanticColor(name)) {
    const swatch = SEMANTIC_COLORS[name];
    return readCssVar(swatch.cssVar) || swatch.fallback;
  }
  return name;
}

/**
 * A background tint for `name`, for DOM surfaces (tiles, cells).
 *
 * The token, not the hex, because unlike `resolveColor` this is only ever used
 * as a CSS value and so does not have to be resolved here. That matters: the
 * ink already followed the theme and the tint did not, so on the dark wall
 * display a status tile kept a pale background under light text -- 1.26:1.
 *
 * A colour that is not one of ours is still tinted here, since there is no
 * token to carry it.
 */
export function washColor(name: string | null | undefined): string {
  if (!name) {
    return "transparent";
  }
  if (isSemanticColor(name)) {
    const swatch = SEMANTIC_COLORS[name];
    return `var(${swatch.washVar}, ${swatch.wash})`;
  }
  return `color-mix(in srgb, ${name} 16%, transparent)`;
}

/*
  The neutral colours a canvas chart draws its own furniture in -- text,
  tracks, rules -- resolved the same way, so a gauge's numbers match the page
  they sit on.
*/
export type UiColor = "ink" | "muted" | "track" | "surface" | "rule";

const UI_COLORS: Record<UiColor, { cssVar: string; fallback: string }> = {
  ink: { cssVar: "--color-text", fallback: "#1c1b1a" },
  muted: { cssVar: "--color-text-muted", fallback: "#6f6b66" },
  track: { cssVar: "--color-surface-sunken", fallback: "#f6f4f1" },
  surface: { cssVar: "--color-surface", fallback: "#ffffff" },
  rule: { cssVar: "--color-border", fallback: "#e8e5e1" },
};

export function uiColor(name: UiColor): string {
  const c = UI_COLORS[name];
  return readCssVar(c.cssVar) || c.fallback;
}
