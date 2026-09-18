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
  /** A tint for backgrounds: a tile, a table cell. */
  wash: string;
}

// Values from client/app/assets/less/inc/tokens.less.
export const SEMANTIC_COLORS: Record<SemanticColor, Swatch> = {
  good: { label: "Good", cssVar: "--color-good", fallback: "#1e7a4c", wash: "#e5f1ea" },
  warning: { label: "Warning", cssVar: "--color-warning", fallback: "#9a6510", wash: "#f7eedd" },
  serious: { label: "Serious", cssVar: "--color-serious", fallback: "#c2560e", wash: "#fbeadf" },
  critical: { label: "Critical", cssVar: "--color-critical", fallback: "#b4342c", wash: "#f8e5e3" },
  neutral: { label: "Neutral", cssVar: "--color-text-muted", fallback: "#6f6b66", wash: "#f1efec" },
  accent: { label: "Accent", cssVar: "--color-action", fallback: "#0a7c93", wash: "#e4f4f7" },
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

/** A background tint for `name`, for DOM surfaces (tiles, cells). */
export function washColor(name: string | null | undefined): string {
  if (!name) {
    return "transparent";
  }
  if (isSemanticColor(name)) {
    return SEMANTIC_COLORS[name].wash;
  }
  return `color-mix(in srgb, ${name} 16%, transparent)`;
}
