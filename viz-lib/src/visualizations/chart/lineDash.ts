/**
 * How a line is drawn, so two series can be told apart without a second colour.
 *
 * A comparison series -- today against the same hour a week ago -- is the same
 * measure twice. Giving it its own colour says it is a different thing; giving
 * it its own *pattern* says it is the same thing at another time, which is what
 * the reader actually needs. That is why this exists, and why solid is the
 * default for every series that has not asked for anything else.
 *
 * ECharts takes a name for its three built-in patterns and an array of numbers
 * for anything else, where the numbers are dash and gap lengths in pixels. The
 * arrays here are used even for `dashed` and `dotted`, whose built-in versions
 * scale with the stroke width: at the 2px a chart line is drawn at, the
 * built-in dotted has a gap shorter than its dot and reads as a textured solid
 * line. These are fixed lengths chosen to stay apart at that width.
 */
export type LineDash = "solid" | "dashed" | "dotted" | "fine" | "long" | "dash-dot";

export const LINE_DASHES: { value: LineDash; name: string; pattern: string | number[] }[] = [
  { value: "solid", name: "Solid", pattern: "solid" },
  { value: "dashed", name: "Dashed", pattern: [8, 5] },
  { value: "dotted", name: "Dotted", pattern: [2, 4] },
  { value: "fine", name: "Fine dots", pattern: [1, 4] },
  { value: "long", name: "Long dash", pattern: [18, 7] },
  { value: "dash-dot", name: "Dash-dot", pattern: [12, 5, 2, 5] },
];

const BY_VALUE = new Map<string, string | number[]>(LINE_DASHES.map(({ value, pattern }) => [value, pattern]));

/** The only series types a dash applies to: the rest have no line to dash. */
export function hasLineDash(seriesType: string | undefined): boolean {
  return seriesType === "line" || seriesType === "area";
}

/**
 * What ECharts should draw for this choice.
 *
 * Solid for anything it does not recognise, which covers a saved chart from
 * before this existed and a hand-edited options blob alike -- neither should
 * turn a chart into dots.
 */
export function dashPattern(dash: unknown): string | number[] {
  return BY_VALUE.get(dash as string) ?? "solid";
}
