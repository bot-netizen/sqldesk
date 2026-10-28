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

/*
  The application's type, for things drawn on a canvas.

  Here for the same reason `uiColor` is: a canvas cannot inherit CSS, so
  anything drawn into one has to be told what the page is using. These were
  copy-pasted into gauge and progress in different orders, and the chart --
  the most-used visualization of the lot -- was told nothing at all, so it
  drew in ECharts' default sans-serif beside tiles drawing in Instrument
  Sans.
*/
export const SANS = '"Instrument Sans Variable", "Instrument Sans", -apple-system, "Segoe UI", sans-serif';
export const MONO = '"JetBrains Mono Variable", "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace';

/*
  The two inks a filled surface can carry. Near-black rather than pure black,
  matching @n-900, so a solid cell does not look heavier than the page around
  it.
*/
const INK_ON_LIGHT = "#1c1b1a";
const INK_ON_DARK = "#ffffff";

/** `#abc`, `#aabbcc`, `rgb(…)` and `rgba(…)` as channels, or null. */
function parseChannels(color: string): [number, number, number] | null {
  const value = (color || "").trim();
  const short = /^#([0-9a-f])([0-9a-f])([0-9a-f])$/i.exec(value);
  if (short) {
    return [short[1], short[2], short[3]].map((c) => parseInt(c + c, 16)) as [number, number, number];
  }
  const long = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(value);
  if (long) {
    return [long[1], long[2], long[3]].map((c) => parseInt(c, 16)) as [number, number, number];
  }
  const functional = /^rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)/i.exec(value);
  if (functional) {
    return [Number(functional[1]), Number(functional[2]), Number(functional[3])];
  }
  return null;
}

function relativeLuminance([r, g, b]: [number, number, number]): number {
  const channel = (c: number) => {
    const v = c / 255;
    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

function contrast(a: number, b: number): number {
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

/**
 * Black or white over `name`, whichever the eye can actually read.
 *
 * Resolved through `resolveColor`, so it reads the live token and follows the
 * theme: the same "critical" fill is a different colour on the wall display,
 * and the ink over it has to be worked out there rather than baked in here.
 *
 * Measured rather than guessed at a lightness threshold, because the two are
 * not the same near the middle: a mid-green and a mid-blue of equal lightness
 * want different inks. When the colour cannot be read at all -- a CSS value
 * this does not parse, a token the page has not defined -- the answer is the
 * dark ink, which is right for every pale fill and the likelier case.
 */
export function contrastInk(name: string | null | undefined): string {
  const channels = parseChannels(resolveColor(name));
  if (!channels) {
    return INK_ON_LIGHT;
  }
  const fill = relativeLuminance(channels);
  const onDark = contrast(fill, relativeLuminance([255, 255, 255]));
  const onLight = contrast(fill, relativeLuminance([28, 27, 26]));
  return onDark > onLight ? INK_ON_DARK : INK_ON_LIGHT;
}

/**
 * The background for `name` at full strength or as a tint.
 *
 * `washColor` is the tint; this adds the other half. A tint is right behind
 * text that has to stay readable, and wrong for a data bar, where the bar
 * *is* the mark and a 16% wash of it is a mark nobody can see.
 *
 * Like `washColor` this hands back the token rather than a resolved hex, so
 * the fill follows the theme.
 */
export function fillColor(name: string | null | undefined, solid: boolean): string {
  if (!name) {
    return "transparent";
  }
  if (!solid) {
    return washColor(name);
  }
  if (isSemanticColor(name)) {
    const swatch = SEMANTIC_COLORS[name];
    return `var(${swatch.cssVar}, ${swatch.fallback})`;
  }
  return name;
}
