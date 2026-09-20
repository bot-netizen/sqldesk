import { formatValue, toNumber, uiColor } from "../shared/valueOptions";
import { AllColorPaletteArrays, resolveColorScheme, DEFAULT_COLOR_SCHEME } from "../ColorPalette";
import { ColumnLike, hasColumn } from "../shared/rows";
import { ECHARTS_MOTION } from "../shared/motion";
import { RadarOptions, MAX_SHAPES } from "./getOptions";
import buildSpokes from "./spokes";

export interface RadarData {
  columns: ColumnLike[];
  rows: any[];
}

export interface BuiltRadar {
  option: any;
  signature: string;
  problem: string | null;
  note: string | null;
}

/** Fewer spokes than this is a line or a triangle, not a web. */
const MIN_SPOKES = 3;

/** Room under the web for the legend, when there is one. */
const LEGEND_HEIGHT = 26;
/** Room outside the web for the spoke names. */
const NAME_ROOM = 24;

/**
 * Where the web sits and how big it is, in pixels.
 *
 * ECharts takes a radar's radius as a percentage of the *whole* canvas, which
 * knows nothing about the legend underneath -- so on a short widget the bottom
 * spoke's name lands on top of the legend. Working in pixels against the box
 * we were given is the only way to reserve that room properly.
 */
export function webLayout(size: { width: number; height: number }, hasLegend: boolean) {
  const reserved = hasLegend ? LEGEND_HEIGHT : 0;
  const usableHeight = Math.max(60, size.height - reserved);
  const radius = Math.max(28, Math.min(size.width, usableHeight) / 2 - NAME_ROOM);
  return { radius, centreY: usableHeight / 2 };
}

export default function buildOption(
  data: RadarData,
  options: RadarOptions,
  size: { width: number; height: number } = { width: 360, height: 300 }
): BuiltRadar {
  const empty = { option: {}, signature: "empty", note: null };
  const rows = (data && data.rows) || [];
  if (!rows.length) {
    return { ...empty, problem: "No rows to show." };
  }

  const spokeColumns = options.valueColumns.filter((name) => hasColumn(data.columns, name));
  if (spokeColumns.length < MIN_SPOKES) {
    return {
      ...empty,
      problem: `Choose at least ${MIN_SPOKES} measures in the editor — a radar needs three spokes to be a radar.`,
    };
  }

  const labelColumn = hasColumn(data.columns, options.labelColumn) ? options.labelColumn : "";
  const shown = rows.slice(0, MAX_SHAPES);
  const spokes = buildSpokes(shown, spokeColumns, options.scaleMode);
  // resolveColorScheme hands back a name, not the colours themselves.
  const palette = (AllColorPaletteArrays as any)[resolveColorScheme(DEFAULT_COLOR_SCHEME)];
  const muted = uiColor("muted");
  const rule = uiColor("rule");
  const web = webLayout(size, options.showLegend);

  const shapes = shown.map((row, index) => ({
    name: labelColumn && row[labelColumn] !== undefined ? String(row[labelColumn]) : `Row ${index + 1}`,
    // ECharts wants one value per spoke, in the spokes' own order. A gap is
    // null, which leaves that corner of the shape open rather than pulling it
    // to zero and inventing a reading.
    value: spokeColumns.map((name) => toNumber(row[name])),
    itemStyle: { color: palette[index % palette.length] },
    areaStyle: options.showArea ? { opacity: 0.18 } : undefined,
  }));

  const format = (v: unknown) => (v === null || v === undefined ? "—" : formatValue(v, options.valueFormat));

  const option = {
    ...ECHARTS_MOTION,
    aria: {
      enabled: true,
      label: {
        description: `A radar of ${spokes.length} measures across ${shapes.length} ${
          shapes.length === 1 ? "row" : "rows"
        }: ${spokes.map((s) => s.name).join(", ")}.`,
      },
    },
    color: palette,
    tooltip: {
      trigger: "item",
      confine: true,
      formatter: (params: any) => {
        const values = params.value || [];
        const lines = spokes.map((spoke, i) => `${spoke.name}: <b>${format(values[i])}</b>`);
        return `${params.name}<br/>${lines.join("<br/>")}`;
      },
    },
    legend: options.showLegend
      ? { bottom: 0, type: "scroll", textStyle: { color: muted }, icon: "roundRect", itemHeight: 8, itemWidth: 12 }
      : { show: false },
    radar: {
      shape: options.shape,
      center: ["50%", web.centreY],
      radius: web.radius,
      // Each spoke states its own end, which is what makes measures in
      // different units comparable at all.
      indicator: spokes.map((s) => ({ name: s.name, max: s.max, min: s.min })),
      axisName: { color: muted, fontSize: 11 },
      splitLine: { lineStyle: { color: rule } },
      axisLine: { lineStyle: { color: rule } },
      splitArea: { show: false },
    },
    series: [
      {
        id: "radar",
        type: "radar",
        data: shapes,
        symbolSize: 4,
        lineStyle: { width: 2 },
        emphasis: { focus: "series", lineStyle: { width: 3 } },
      },
    ],
  };

  const note =
    rows.length > shown.length
      ? `Showing the first ${shown.length} of ${rows.length} rows; more than that is a smudge.`
      : null;

  // The spokes and the shapes' names are the shape; new readings can tween.
  const signature = JSON.stringify([
    spokes.map((s) => [s.name, s.max, s.min]),
    shapes.map((s) => s.name),
    options.shape,
    options.showArea,
    options.showLegend,
    Math.round(web.radius),
  ]);

  return { option, signature, problem: null, note };
}
