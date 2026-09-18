import { toNumber } from "./format";
import { isSemanticColor } from "./colors";

/*
  Thresholds colour a value by where it falls. The model is Grafana's, because
  it is the one people already know: a base colour for everything, then steps,
  each taking over from its value upwards.

    base: good,  steps: [{ value: 250, color: warning }, { value: 400, color: critical }]

  reads as "good below 250, warning from 250, critical from 400".
*/

export interface ThresholdStep {
  value: number;
  color: string;
}

export interface Thresholds {
  base: string;
  steps: ThresholdStep[];
}

export const DEFAULT_THRESHOLDS: Thresholds = { base: "good", steps: [] };

export function normalizeThresholds(thresholds?: Partial<Thresholds> | null): Thresholds {
  const base =
    thresholds && typeof thresholds.base === "string" && thresholds.base ? thresholds.base : DEFAULT_THRESHOLDS.base;
  const steps = (thresholds && Array.isArray(thresholds.steps) ? thresholds.steps : [])
    .map((s) => ({ value: toNumber(s && s.value), color: s && typeof s.color === "string" ? s.color : "neutral" }))
    .filter((s): s is ThresholdStep => s.value !== null)
    .sort((a, b) => a.value - b.value);
  return { base, steps };
}

export function hasThresholds(thresholds?: Partial<Thresholds> | null): boolean {
  return normalizeThresholds(thresholds).steps.length > 0;
}

/** The colour name for `value`, or null when the value is not a number. */
export function thresholdColor(value: unknown, thresholds?: Partial<Thresholds> | null): string | null {
  const n = toNumber(value);
  if (n === null) {
    return null;
  }
  const { base, steps } = normalizeThresholds(thresholds);
  let color = base;
  for (const step of steps) {
    if (n >= step.value) {
      color = step.color;
    }
  }
  return color;
}

/**
 * The bands between `min` and `max`, as fractions of the range -- what a gauge
 * draws along its arc. Steps outside the range are clamped; a range of zero
 * width yields one band in the base colour.
 */
export function thresholdBands(
  thresholds: Partial<Thresholds> | null | undefined,
  min: number,
  max: number
): { to: number; color: string }[] {
  const { base, steps } = normalizeThresholds(thresholds);
  const span = max - min;
  if (!(span > 0)) {
    return [{ to: 1, color: base }];
  }
  // Walk up the range: each step closes the band below it in the colour that
  // was current, then becomes the current colour itself.
  const bands: { to: number; color: string }[] = [];
  let color = base;
  let cursor = 0;
  for (const step of steps) {
    const at = Math.max(0, Math.min(1, (step.value - min) / span));
    if (at > cursor) {
      bands.push({ to: at, color });
      cursor = at;
    }
    color = step.color;
  }
  if (cursor < 1) {
    bands.push({ to: 1, color });
  }
  return bands;
}

/** A colour that is one of ours, for code paths that only understand those. */
export function severityOf(
  color: string | null
): "good" | "warning" | "serious" | "critical" | "neutral" | "accent" | null {
  return isSemanticColor(color) ? color : null;
}
