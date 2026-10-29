/**
 * Stacked panels: several plots sharing one x axis.
 *
 * The chart somebody asks for when they want spend over time, the percent
 * change against last week, and a pair of rates -- all against the same
 * clock, read down a single column. Three charts side by side cannot do it,
 * because the eye has to carry a time position between them; three panels
 * can, because the time position is the same place on the page.
 *
 * Deliberately two settings and no more: how many panels, and which one a
 * series is in. Per-panel titles and heights were built and then cut -- they
 * doubled the editor surface for a chart form most people never reach for,
 * and the titles clipped off the left edge whenever a panel's numbers were
 * narrow. What is left is the part nothing else in the application can do:
 * plots on different scales under one cursor and one x extent. A second y
 * axis already handles two scales in one plot, and a column of dashboard
 * widgets already stacks charts -- neither shares a cursor.
 *
 * Redash's answer to this was a textarea of Plotly JavaScript behind a server
 * flag. ECharts lays panels out from a `grid` array natively, so the answer
 * here is a number and a per-series choice: no user code to review.
 *
 * Panels are for upright cartesian charts. A pie has no grid, a heatmap builds
 * its own, and a sideways bar chart runs its categories down the axis that
 * panels would divide -- so each of those draws as one panel whatever is
 * saved.
 */
import { isFinite, map, range } from "lodash";

/**
 * Four, because the fourth panel of a dashboard widget is already around
 * fifty pixels tall. The limit is about what can be read, not what ECharts
 * can lay out.
 */
export const MAX_PANELS = 4;

/** Between two panels: room for the lower one's topmost value label. */
const PANEL_GAP = 26;

/**
 * Assumed height while the container has not been measured.
 *
 * The single-panel grid never needed this -- it pins top and bottom and lets
 * the middle stretch -- but a panel has to be told its height, and a height
 * needs a number. One frame later `useElementSize` reports the real one and
 * the chart is rebuilt, so this only ever decides the first paint.
 */
const NOMINAL_HEIGHT = 320;

/**
 * How many panels this chart draws.
 *
 * Clamped rather than trusted: `panels` comes out of saved JSON, which can
 * hold anything at all, and a zero or a negative would produce a grid array
 * with no grids in it and an empty chart.
 */
export function panelCount(options: any): number {
  const saved = Number(options && options.panels);
  if (!isFinite(saved) || saved <= 1) {
    return 1;
  }
  return Math.min(MAX_PANELS, Math.floor(saved));
}

/**
 * Which panel a series sits in.
 *
 * Out-of-range lands in the first panel rather than nowhere: a series whose
 * panel was deleted by turning the count down has to be drawn somewhere, and
 * the top panel is where it can be seen and moved.
 */
export function seriesPanel(seriesName: string, options: any, count: number): number {
  if (count <= 1) {
    return 0;
  }
  const saved = Number((options.seriesOptions[seriesName] || {}).panel);
  if (!isFinite(saved) || saved < 0 || saved >= count) {
    return 0;
  }
  return Math.floor(saved);
}

export interface PanelBand {
  /** Pixels above the first panel. */
  top: number;
  /** Pixels below the last panel: legend, zoom slider, x axis. */
  bottom: number;
  /** The measured height of the container, or 0 when it is not known yet. */
  height: number;
}

export interface PanelBox {
  top: number;
  height: number;
}

/**
 * Where each panel sits, top to bottom.
 *
 * Equal shares, with the gaps taken out of the space before it is divided so
 * every plot is the same height rather than every plot-plus-gap.
 *
 * Panels are not given a floor. A widget two rows tall divided three ways
 * produces three unreadable strips, and that is the honest result of asking
 * for it: collapsing to one panel instead would draw something other than
 * what the chart says it draws, and the fix -- a taller widget -- is not
 * discoverable from a chart that silently ignored the setting.
 */
export function panelBoxes(count: number, band: PanelBand): PanelBox[] {
  const height = band.height || NOMINAL_HEIGHT;
  const gaps = PANEL_GAP * (count - 1);
  // One pixel a panel is the floor for the arithmetic, not for legibility:
  // below it the shares go negative and ECharts draws grids upside down.
  const available = Math.max(count, height - band.top - band.bottom - gaps);
  const each = available / count;

  return map(range(count), (index) => ({ top: band.top + index * (each + PANEL_GAP), height: each }));
}

/**
 * The index of a series' measure axis.
 *
 * Every panel keeps the left-and-right pair a single-panel chart has, so the
 * axes run left, right, left, right down the stack and a series needs both
 * its panel and its side to find the right one.
 */
export function measureAxisIndex(panel: number, side: 0 | 1): number {
  return panel * 2 + side;
}
