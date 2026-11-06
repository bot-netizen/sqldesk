import moment from "moment";
import { each, map } from "lodash";
import escapeHtml from "@/lib/escapeHtml";
import { ECHARTS_MOTION } from "@/visualizations/shared/motion";
import { NO_ROWS } from "@/visualizations/shared/components/Problem";
import { createNumberFormatter } from "@/lib/value-format";
import { CandlestickOptions } from "./getOptions";

/*
  Open, close, low, high -- four numbers a line chart throws away.

  A line of closing prices says where something ended each day and nothing
  about what it did on the way: a day that opened at 10, fell to 2, and
  recovered to 11 draws the same stroke as a day that drifted from 10 to 11.
  The candle keeps the range and the direction, which is the whole reason
  the shape exists.

  ECharts wants [open, close, low, high] in that order. Written out
  explicitly here because every other convention in the world says OHLC,
  and a silent transposition draws a plausible chart of the wrong thing.
*/

export interface BuiltCandlestick {
  option: any;
  signature: string;
  problem: string | null;
}

/** [open, close, low, high] -- ECharts' order, not OHLC. */
export type Candle = [number, number, number, number];

export function problemWith(data: any, options: CandlestickOptions): string | null {
  if (!data || !data.rows || data.rows.length === 0) {
    return NO_ROWS;
  }
  const missing = ["openColumn", "closeColumn", "lowColumn", "highColumn"].filter((key) => !(options as any)[key]);
  if (!options.xColumn || missing.length) {
    return "This needs a column for the axis and one each for open, close, low and high.";
  }
  return null;
}

/** A date reads as a date; anything else stays the label it was. */
export function axisLabel(value: any): string {
  if (moment.isMoment(value)) {
    return value.isValid() ? value.format("YYYY-MM-DD") : String(value);
  }
  if (value instanceof Date) {
    return moment.utc(value).format("YYYY-MM-DD");
  }
  return value === null || value === undefined ? "" : String(value);
}

function asNumber(value: any): number | null {
  // `Number(null)` is 0 and `Number("")` is 0, both finite -- so a missing
  // low would survive as a candle stretching to the axis, which reads as a
  // crash that never happened. The emptiness has to be caught before the
  // coercion, not after it.
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

/**
 * Rows into candles, keeping the axis labels alongside.
 *
 * A row missing any of the four is dropped rather than zero-filled: a
 * candle with a zero low is a bar stretching to the axis, which reads as a
 * crash that never happened.
 */
export function candlesFrom(rows: any[], options: CandlestickOptions): { labels: string[]; candles: Candle[] } {
  const labels: string[] = [];
  const candles: Candle[] = [];
  each(rows, (row) => {
    const open = asNumber(row[options.openColumn]);
    const close = asNumber(row[options.closeColumn]);
    const low = asNumber(row[options.lowColumn]);
    const high = asNumber(row[options.highColumn]);
    if (open === null || close === null || low === null || high === null) {
      return;
    }
    labels.push(axisLabel(row[options.xColumn]));
    candles.push([open, close, low, high]);
  });
  return { labels, candles };
}

export default function buildOption(data: any, rawOptions: CandlestickOptions): BuiltCandlestick {
  const problem = problemWith(data, rawOptions);
  if (problem) {
    return { option: { series: [] }, signature: "invalid", problem };
  }

  const { labels, candles } = candlesFrom(data.rows, rawOptions);
  if (!candles.length) {
    return {
      option: { series: [] },
      signature: "empty",
      problem: "No row has all four of open, close, low and high.",
    };
  }

  const format = createNumberFormatter(rawOptions.valueFormat);

  const option = {
    ...ECHARTS_MOTION,
    tooltip: {
      trigger: "axis",
      confine: true,
      axisPointer: { type: "line" },
      formatter: (params: any) => {
        const item = (Array.isArray(params) ? params[0] : params) || {};
        // ECharts prepends the datum's index, so the four numbers start at 1.
        const [, open, close, low, high] = item.value || [];
        return [
          `<div style="font-weight:600;margin-bottom:2px">${escapeHtml(String(item.name))}</div>`,
          `Open: ${escapeHtml(format(open))}`,
          `Close: ${escapeHtml(format(close))}`,
          `Low: ${escapeHtml(format(low))}`,
          `High: ${escapeHtml(format(high))}`,
        ].join("<br/>");
      },
    },
    grid: { left: 12, right: 12, top: 16, bottom: 24, containLabel: true },
    xAxis: { type: "category", data: labels, axisLabel: { hideOverlap: true } },
    // Never from zero: a candlestick is about the range things moved
    // through, and anchoring the axis at zero squashes every candle into a
    // band at the top where none of it can be read.
    yAxis: { type: "value", scale: true, axisLabel: { formatter: (value: any) => format(value) } },
    series: [
      {
        id: "candlestick",
        type: "candlestick",
        data: candles,
        itemStyle: {
          color: rawOptions.risingColor,
          color0: rawOptions.fallingColor,
          borderColor: rawOptions.risingColor,
          borderColor0: rawOptions.fallingColor,
        },
      },
    ],
  };

  return { option, signature: JSON.stringify([labels.length, map(labels, (l) => l).slice(0, 1)]), problem: null };
}
