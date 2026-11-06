import { DEFAULT_VALUE_FORMAT, ValueFormat, normalizeValueFormat } from "../shared/valueOptions";
import { ColumnLike, defaultLabelColumn, numericColumns } from "../shared/rows";

export interface CandlestickOptions {
  /** What runs along the axis. Usually a date. */
  xColumn: string;
  openColumn: string;
  closeColumn: string;
  lowColumn: string;
  highColumn: string;
  /** Up and down are the whole convention; which way round is not universal. */
  risingColor: string;
  fallingColor: string;
  valueFormat: ValueFormat;
}

/** Green up, red down -- the convention most of the world reads. */
export const DEFAULT_RISING = "#16a34a";
export const DEFAULT_FALLING = "#dc2626";

export const DEFAULT_CANDLESTICK_OPTIONS = {
  risingColor: DEFAULT_RISING,
  fallingColor: DEFAULT_FALLING,
  valueFormat: DEFAULT_VALUE_FORMAT,
};

export default function getOptions(options: any, data?: { columns: ColumnLike[]; rows: any[] }): CandlestickOptions {
  const o = { ...DEFAULT_CANDLESTICK_OPTIONS, ...(options || {}) };
  const columns = data ? data.columns : [];
  const rows = data ? data.rows : [];
  const numbers = numericColumns(columns, rows).map((column) => column.name);

  // Four numeric columns in the order a candle is read. Guessing them by
  // position rather than by name, because a query writes `o, c, l, h` as
  // often as it writes the words out, and four empty selects is a worse
  // first impression than four that need correcting.
  const [first, second, third, fourth] = numbers;

  return {
    ...o,
    xColumn: o.xColumn || defaultLabelColumn(columns, rows),
    openColumn: o.openColumn || first || "",
    closeColumn: o.closeColumn || second || "",
    lowColumn: o.lowColumn || third || "",
    highColumn: o.highColumn || fourth || "",
    risingColor: o.risingColor || DEFAULT_RISING,
    fallingColor: o.fallingColor || DEFAULT_FALLING,
    valueFormat: normalizeValueFormat(o.valueFormat),
  };
}
