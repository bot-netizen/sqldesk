import moment from "moment";
import { formatValue, resolveColor, uiColor } from "../shared/valueOptions";
import { ColumnLike, hasColumn } from "../shared/rows";
import { ECHARTS_MOTION } from "../shared/motion";
import { CalendarOptions } from "./getOptions";
import buildDays, { yearsIn, DAY } from "./days";

export interface CalendarData {
  columns: ColumnLike[];
  rows: any[];
}

export interface BuiltCalendar {
  option: any;
  signature: string;
  problem: string | null;
  note: string | null;
}

/** Room above the squares for the month names, and below for the scale. */
const HEADER = 28;
const SCALE_HEIGHT = 34;
/** A square smaller than this is a speck; bigger than this is a wall of tiles. */
const MIN_CELL = 8;
const MAX_CELL = 22;

/**
 * How big each day's square can be, and where each year's row sits.
 *
 * A calendar has a fixed shape -- seven rows of days, as many columns as there
 * are weeks -- so unlike most charts it cannot simply stretch. The square size
 * is whichever of the width and the height allows less, and the years are
 * stacked from there.
 */
export function layout(size: { width: number; height: number }, years: number, weeks: number) {
  const usableHeight = Math.max(40, size.height - SCALE_HEIGHT) / Math.max(1, years);
  const byHeight = (usableHeight - HEADER) / 7;
  // Room down each side for the weekday names.
  const byWidth = (size.width - 56) / Math.max(1, weeks);
  const cell = Math.round(Math.max(MIN_CELL, Math.min(MAX_CELL, Math.min(byHeight, byWidth))));
  return { cell, rowHeight: cell * 7 + HEADER };
}

export default function buildOption(
  data: CalendarData,
  options: CalendarOptions,
  size: { width: number; height: number } = { width: 720, height: 240 }
): BuiltCalendar {
  const empty = { option: {}, signature: "empty", note: null };
  const rows = (data && data.rows) || [];
  if (!rows.length) {
    return { ...empty, problem: "No rows to show." };
  }
  if (!hasColumn(data.columns, options.dateColumn)) {
    return { ...empty, problem: "Choose a date column in the editor." };
  }

  const valueColumn = hasColumn(data.columns, options.valueColumn) ? options.valueColumn : "";
  const built = buildDays(rows, options.dateColumn, valueColumn, options.range);
  if (!built.days.length) {
    return { ...empty, problem: `No readable dates in “${options.dateColumn}”.` };
  }

  const years = yearsIn(built.from, built.to);
  const weeks = Math.ceil((moment(built.to, DAY).diff(moment(built.from, DAY), "days") + 1) / 7) + 1;
  const { cell, rowHeight } = layout(size, years.length, Math.min(weeks, 53));

  const values = built.days.map((d) => d.value);
  const low = Math.min(...values);
  const high = Math.max(...values);
  const muted = uiColor("muted");
  const rule = uiColor("rule");
  const track = uiColor("track");
  const strong = resolveColor(options.color, "accent");
  const format = (v: number) => formatValue(v, options.valueFormat);

  // One calendar per year, so a span crossing new year reads as two rows of
  // twelve months rather than one strip of a hundred weeks.
  const calendars = years.map((year, index) => {
    const from = index === 0 ? built.from : `${year}-01-01`;
    const to = index === years.length - 1 ? built.to : `${year}-12-31`;
    return {
      top: 18 + index * rowHeight,
      left: 40,
      right: 12,
      cellSize: [cell, cell],
      range: [from, to],
      splitLine: { show: false },
      itemStyle: { color: track, borderColor: rule, borderWidth: 1 },
      yearLabel: { show: years.length > 1, position: "top", color: muted, fontSize: 11 },
      monthLabel: { color: muted, fontSize: 10, nameMap: "en" },
      dayLabel: { color: muted, fontSize: 10, nameMap: "en", firstDay: options.startOnMonday ? 1 : 0 },
    };
  });

  const option = {
    ...ECHARTS_MOTION,
    aria: {
      enabled: true,
      label: {
        description: `A calendar from ${built.from} to ${built.to}: ${built.days.length} days with data, from ${format(
          low
        )} to ${format(high)}.`,
      },
    },
    tooltip: {
      trigger: "item",
      confine: true,
      formatter: (params: any) => {
        const [date, value] = params.value;
        return `${moment(date, DAY).format("D MMMM YYYY")}<br/><b>${format(value)}</b>`;
      },
    },
    visualMap: {
      type: "continuous",
      min: low,
      max: high === low ? low + 1 : high,
      calculable: false,
      orient: "horizontal",
      left: 40,
      bottom: 0,
      itemWidth: 10,
      itemHeight: 90,
      text: [format(high), format(low)],
      textStyle: { color: muted, fontSize: 10 },
      inRange: { color: [track, strong] },
    },
    calendar: calendars,
    series: years.map((year, index) => ({
      id: `calendar:${year}`,
      type: "heatmap",
      coordinateSystem: "calendar",
      calendarIndex: index,
      data: built.days.filter((d) => moment(d.date, DAY).year() === year).map((d) => [d.date, d.value]),
      itemStyle: { borderColor: uiColor("surface"), borderWidth: 1 },
    })),
  };

  const left: string[] = [];
  if (built.undated > 0) {
    left.push(`${built.undated} row${built.undated === 1 ? "" : "s"} had no readable date`);
  }
  if (built.skipped > 0) {
    left.push(`${built.skipped} had no number in “${options.valueColumn}”`);
  }
  const note = left.length ? `${left.join(", ")}.` : null;

  // The span and the layout are the shape; new values for the same days tween.
  const signature = JSON.stringify([built.from, built.to, years, cell, options.color, options.startOnMonday]);

  return { option, signature, problem: null, note };
}
