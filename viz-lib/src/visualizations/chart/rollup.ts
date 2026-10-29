/**
 * What happens when several rows share an x.
 *
 * A query keyed on region, channel and product returns several rows per
 * region. Plot region against the sum and the chart has to do something with
 * the duplicates, and it always has: it added them up. That is usually right
 * for money and almost never right for a rate -- the average of four
 * conversion rates is a conversion rate, their sum is nothing at all -- and
 * until now there was no way to say so, and no sign on the chart that any of
 * it was happening.
 *
 * So the behaviour is unchanged and now has a name. `sum` is the default,
 * every saved chart keeps the numbers it was drawing, and the editor says
 * out loud what it is doing to the rows.
 */
export type Rollup = "sum" | "average" | "min" | "max" | "count";

export const ROLLUPS: { value: Rollup; name: string; help: string }[] = [
  { value: "sum", name: "Add them up", help: "Totals, revenue, counts of things." },
  { value: "average", name: "Average them", help: "Rates and ratios, where a total means nothing." },
  { value: "min", name: "Keep the lowest", help: "The worst case at each point." },
  { value: "max", name: "Keep the highest", help: "The peak at each point." },
  { value: "count", name: "Count the rows", help: "How many rows share this x, ignoring the measure." },
];

const NAMES = new Set<string>(ROLLUPS.map(({ value }) => value));

/**
 * The rollup a chart uses.
 *
 * Anything unrecognised is `sum`, which is what every chart saved before this
 * existed was already doing. A chart must not change its numbers because a
 * options blob holds a word this version does not know.
 */
export function rollupMode(options: any): Rollup {
  const saved = options && options.rollup;
  return NAMES.has(saved) ? (saved as Rollup) : "sum";
}

/**
 * Running state for one x position.
 *
 * `count` is kept for every mode because `average` needs it, and keeping it
 * always is cheaper than deciding whether to.
 */
export interface RollupState {
  total: number;
  /** Rows at this x, whether or not they carried a number. */
  count: number;
  /** Rows at this x that carried a number, which is what an average divides by. */
  values: number;
  min: number | null;
  max: number | null;
}

export function startRollup(): RollupState {
  return { total: 0, count: 0, values: 0, min: null, max: null };
}

/**
 * Fold one row in.
 *
 * A null measure still counts as a row, because `count` is about rows and not
 * about values -- "how many orders in this region" is a question about rows,
 * and one with a null total is still an order.
 */
export function addToRollup(state: RollupState, value: number | null | undefined): RollupState {
  state.count += 1;
  if (value === null || value === undefined || !isFinite(value)) {
    return state;
  }
  state.values += 1;
  state.total += value;
  state.min = state.min === null ? value : Math.min(state.min, value);
  state.max = state.max === null ? value : Math.max(state.max, value);
  return state;
}

/**
 * What the chart draws at this x.
 *
 * Null where there is nothing to draw, rather than zero: a region with no
 * readings is a gap in the line, and drawing it at zero says the measure was
 * zero, which is a different and much worse claim. `count` is the exception
 * -- it is about rows, and a row with no number is still a row.
 */
export function finishRollup(state: RollupState, mode: Rollup): number | null {
  if (mode === "count") {
    return state.count;
  }
  if (!state.values) {
    return null;
  }
  switch (mode) {
    case "average":
      // Over the rows that had a number. Dividing by the rows that did not
      // would quietly read every missing reading as a zero.
      return state.total / state.values;
    case "min":
      return state.min;
    case "max":
      return state.max;
    default:
      return state.total;
  }
}
