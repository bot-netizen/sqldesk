import { isNil } from "lodash";

// ECharts has no error-bar series, and none of the eight official custom series
// is one either. This draws them with `renderItem`, which is the documented way
// to add a mark type the library does not ship.

// A custom series is positioned in data space, while bars are packed inside the
// category band -- so to put a mark on a bar we have to know the packing. These
// are set explicitly on the bar series rather than left to ECharts: version 6
// changed the defaults, and measuring showed the marks landing 18px beside
// their bars. Pinning both makes the geometry ours, so the two cannot drift.
export const BAR_CATEGORY_GAP = 0.2;
export const BAR_GAP = 0.3;

/** The same two numbers, in the form the bar series wants them. */
export const BAR_LAYOUT = {
  barCategoryGap: `${BAR_CATEGORY_GAP * 100}%`,
  barGap: `${BAR_GAP * 100}%`,
};

/**
 * Where the centre of one bar sits, as a fraction of the category band.
 *
 * 0 is the middle of the band. With a single series the bar is centred, so this
 * is 0 and the error bar needs no offset at all.
 */
export function barCentreOffset(index: number, count: number): number {
  if (count <= 1) {
    return 0;
  }
  const usable = 1 - BAR_CATEGORY_GAP;
  const barWidth = usable / (count + (count - 1) * BAR_GAP);
  const left = -usable / 2;
  return left + index * barWidth * (1 + BAR_GAP) + barWidth / 2;
}

function renderErrorBar(params: any, api: any) {
  const value = api.value(1);
  const error = api.value(2);
  const offset = api.value(3);
  if (isNil(value) || isNil(error) || !isFinite(error) || error === 0) {
    return null;
  }

  const band = api.size([1, 0])[0];
  const shift = band * offset;
  const high = api.coord([api.value(0), value + error]);
  const low = api.coord([api.value(0), value - error]);
  // Caps a quarter of a category wide, capped so a sparse axis does not draw
  // caps wider than the chart.
  const cap = Math.min(band * 0.12, 10);

  const style = {
    stroke: api.visual("color"),
    fill: undefined,
    lineWidth: 1.5,
  };
  const line = (x1: number, y1: number, x2: number, y2: number) => ({
    type: "line",
    // Named so ECharts tweens the bar between updates instead of redrawing it.
    transition: ["shape"],
    shape: { x1, y1, x2, y2 },
    style,
  });

  return {
    type: "group",
    children: [
      line(high[0] + shift - cap, high[1], high[0] + shift + cap, high[1]),
      line(high[0] + shift, high[1], low[0] + shift, low[1]),
      line(low[0] + shift - cap, low[1], low[0] + shift + cap, low[1]),
    ],
  };
}

export interface ErrorBarPoint {
  /** Data-space x, or the category index on a category axis. */
  x: any;
  y: number | null;
  yError: number | null;
}

/**
 * A custom series drawing the ± bars for one data series.
 *
 * Returns null when nothing has an error value, so charts without an errors
 * column pay nothing for this.
 */
export function buildErrorBarSeries(
  id: string,
  name: string,
  points: ErrorBarPoint[],
  color: string,
  yAxisIndex: number,
  offset: number
) {
  const data = points
    .filter((point) => !isNil(point.y) && !isNil(point.yError) && point.yError !== 0)
    .map((point) => [point.x, point.y, point.yError, offset]);

  if (data.length === 0) {
    return null;
  }

  return {
    id: `${id}:error`,
    name,
    type: "custom",
    data,
    yAxisIndex,
    renderItem: renderErrorBar,
    itemStyle: { color },
    // Above the bars and lines they annotate.
    z: 5,
    legendHoverLink: false,
    tooltip: { show: false },
    silent: true,
  };
}
