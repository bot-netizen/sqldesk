import moment from "moment";
import { findMapping, resolveColor, uiColor } from "../shared/valueOptions";
import { AllColorPaletteArrays, resolveColorScheme, DEFAULT_COLOR_SCHEME } from "../ColorPalette";
import { ColumnLike, hasColumn } from "../shared/rows";
import { ECHARTS_MOTION } from "../shared/motion";
import { TimelineOptions } from "./getOptions";
import buildSpans, { Span } from "./spans";

export interface TimelineData {
  columns: ColumnLike[];
  rows: any[];
}

export interface BuiltTimeline {
  option: any;
  signature: string;
  problem: string | null;
  note: string | null;
}

/** How much of a lane's height a bar fills. */
const BAR_HEIGHT = 0.62;
/** A bar narrower than this is still drawn, so a brief state is not lost. */
const MIN_BAR_WIDTH = 2;

/**
 * Bars of state along time.
 *
 * Drawn with `renderItem` because no ECharts series puts a rectangle between
 * two arbitrary times on a category lane: a bar series starts at the axis, and
 * stacking invisible bars to fake an offset breaks the moment the lanes are a
 * category axis rather than a numeric one.
 */
function renderSpan(params: any, api: any) {
  const lane = api.value(0);
  const from = api.value(1);
  const to = api.value(2);
  if (!isFinite(from) || !isFinite(to)) {
    return null;
  }

  const start = api.coord([from, lane]);
  const end = api.coord([to, lane]);
  const height = api.size([0, 1])[1] * BAR_HEIGHT;
  const width = Math.max(end[0] - start[0], MIN_BAR_WIDTH);

  const shape = {
    x: start[0],
    y: start[1] - height / 2,
    width,
    height,
    r: 2,
  };

  return {
    type: "rect",
    // Named so ECharts tweens a bar to its new place instead of redrawing it.
    transition: ["shape"],
    // Without clipping, a span running off the side of the window is drawn
    // over the axis labels.
    shape: { ...shape, ...clipToGrid(shape, params) },
    style: api.style(),
  };
}

/** Trim a rectangle to the plot area, the way ECharts' own examples do. */
function clipToGrid(shape: { x: number; width: number }, params: any) {
  const coordSys = params.coordSys || {};
  const left = coordSys.x || 0;
  const right = left + (coordSys.width || 0);
  const x = Math.max(shape.x, left);
  const width = Math.min(shape.x + shape.width, right) - x;
  return { x, width: Math.max(width, 0) };
}

function spanColor(span: Span, options: TimelineOptions, palette: string[], stateIndex: Map<string, number>): string {
  const mapping = findMapping(span.state, options.mappings);
  if (mapping && mapping.color) {
    return resolveColor(mapping.color);
  }
  if (!span.state) {
    return resolveColor(options.defaultColor, "accent");
  }
  // An unmapped state still needs telling apart from its neighbours, so it
  // takes the next colour off the palette rather than all of them sharing one.
  const index = stateIndex.get(span.state) || 0;
  return palette[index % palette.length];
}

export default function buildOption(data: TimelineData, options: TimelineOptions): BuiltTimeline {
  const empty = { option: {}, signature: "empty", note: null };
  const rows = (data && data.rows) || [];
  if (!rows.length) {
    return { ...empty, problem: "No rows to show." };
  }
  if (!hasColumn(data.columns, options.startColumn)) {
    return { ...empty, problem: "Choose a start time column in the editor." };
  }

  const built = buildSpans({
    rows,
    laneColumn: hasColumn(data.columns, options.laneColumn) ? options.laneColumn : "",
    startColumn: options.startColumn,
    endColumn: hasColumn(data.columns, options.endColumn) ? options.endColumn : "",
    durationColumn: hasColumn(data.columns, options.durationColumn) ? options.durationColumn : "",
    stateColumn: hasColumn(data.columns, options.stateColumn) ? options.stateColumn : "",
  });
  if (!built.spans.length) {
    return { ...empty, problem: `No readable times in “${options.startColumn}”.` };
  }

  const palette = (AllColorPaletteArrays as any)[resolveColorScheme(DEFAULT_COLOR_SCHEME)];
  const muted = uiColor("muted");
  const rule = uiColor("rule");

  // Each distinct state gets its own place in the palette, assigned in the
  // order the states appear so a refresh does not recolour the chart.
  const stateIndex = new Map<string, number>();
  built.spans.forEach((span) => {
    if (span.state && !stateIndex.has(span.state)) {
      stateIndex.set(span.state, stateIndex.size);
    }
  });

  const stamp = (ms: number) => moment(ms).format(options.timeFormat);

  const option = {
    ...ECHARTS_MOTION,
    aria: {
      enabled: true,
      label: {
        description: `A timeline of ${built.spans.length} spans across ${built.lanes.length} ${
          built.lanes.length === 1 ? "track" : "tracks"
        }, from ${stamp(built.from)} to ${stamp(built.to)}.`,
      },
    },
    grid: { left: 8, right: 16, top: 12, bottom: 8, containLabel: true },
    tooltip: {
      trigger: "item",
      confine: true,
      formatter: (params: any) => {
        const span = built.spans[params.dataIndex];
        if (!span) {
          return "";
        }
        const minutes = (span.to - span.from) / 60000;
        const length = minutes >= 1 ? `${minutes.toFixed(minutes >= 10 ? 0 : 1)} min` : `${Math.round(minutes * 60)} s`;
        return [
          span.lane ? `<b>${span.lane}</b>` : null,
          span.state ? findMapping(span.state, options.mappings)?.text || span.state : null,
          `${stamp(span.from)} → ${span.open ? "still going" : stamp(span.to)}`,
          `${length}${span.open ? " so far" : ""}`,
        ]
          .filter(Boolean)
          .join("<br/>");
      },
    },
    xAxis: {
      type: "time",
      min: built.from,
      max: built.to,
      axisLabel: { color: muted, hideOverlap: true },
      splitLine: { show: true, lineStyle: { color: rule } },
    },
    yAxis: {
      type: "category",
      data: built.lanes,
      // Lanes read top to bottom in the order the query returned them, which
      // is the order a category axis draws bottom-up by default.
      inverse: true,
      axisLabel: { color: muted },
      axisTick: { show: false },
      splitLine: { show: false },
    },
    series: [
      {
        id: "spans",
        type: "custom",
        renderItem: renderSpan,
        // The lane, then the two times the rectangle spans.
        encode: { x: [1, 2], y: 0 },
        data: built.spans.map((span) => ({
          value: [built.lanes.indexOf(span.lane), span.from, span.to],
          itemStyle: {
            color: spanColor(span, options, palette, stateIndex),
            // A run still going is outlined, so it is visibly unfinished
            // rather than just a bar that happens to reach the right edge.
            borderColor: span.open ? uiColor("ink") : "transparent",
            borderWidth: span.open ? 1 : 0,
            borderType: span.open ? "dashed" : "solid",
          },
        })),
        label: options.showLabels
          ? {
              show: true,
              position: "insideLeft",
              formatter: (params: any) => {
                const span = built.spans[params.dataIndex];
                const mapping = findMapping(span.state, options.mappings);
                return (mapping && mapping.text) || span.state || "";
              },
              color: "#fff",
              fontSize: 11,
              overflow: "truncate",
            }
          : { show: false },
      },
    ],
  };

  const note =
    built.undated > 0
      ? `${built.undated} row${built.undated === 1 ? "" : "s"} had no readable time in “${options.startColumn}”.`
      : null;

  // The lanes and the states are the shape; new times for the same spans tween.
  const signature = JSON.stringify([
    built.lanes,
    [...stateIndex.keys()],
    built.spans.length,
    options.showLabels,
    options.mappings,
  ]);

  return { option, signature, problem: null, note };
}
