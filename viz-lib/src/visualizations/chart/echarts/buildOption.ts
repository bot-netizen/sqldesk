import { each, extend, filter, isNil, map, max, reduce, some, sortBy, uniq } from "lodash";
import { AllColorPaletteArrays, resolveColorScheme } from "@/visualizations/ColorPalette";
import { createNumberFormatter, formatSimpleTemplate } from "@/lib/value-format";
import chooseTextColorForBackground from "@/lib/chooseTextColorForBackground";
import { cleanNumber, echartsAxisType, getSeriesAxisIndex, normalizeX, seriesId } from "./utils";
import { DEFAULT_HEAT_RAMP, HEAT_RAMPS } from "./heatRamps";
import { buildBoxSeries } from "./boxplot";
import { BAR_LAYOUT, barCentreOffset, buildErrorBarSeries } from "./errorBars";
import { applyWindow, addReferences, zoomComponents } from "./references";

// Deliberately free of any `echarts` import. Keeping the option builder pure
// means it is unit-testable without a canvas, and without Jest having to
// transform ECharts' ESM build.

export interface BuiltOption {
  option: any;
  /**
   * The shape of the chart: its series and its categories. When this is
   * unchanged between renders, new data can be merged in and ECharts animates
   * from the old values to the new ones. When it changes, the points no longer
   * mean the same thing and merging would tween between unrelated values.
   */
  signature: string;
}

const AXIS_LABEL_LIMIT = 120;

/**
 * Past this many bars, a label each is not legible at any angle, so ECharts
 * goes back to showing the ones that fit. Mush helps nobody.
 */
export const MAX_LABELLED_CATEGORIES = 50;

/**
 * How far to tip the category labels so all of them fit.
 *
 * Showing every label means they can collide, and ECharts will not rotate on
 * its own. This is an estimate from the labels themselves -- roughly seven
 * pixels a character at the default font -- because the real width of the
 * chart is not known until it is drawn.
 *
 * 45 degrees and nothing steeper: tried against the real renderer, upright
 * labels collide well before that, and at 90 they read bottom-to-top, which is
 * worse than tilted even though it packs tighter.
 */
export function categoryLabelRotation(categories: any[]): number {
  const needed = reduce(categories, (total, category) => total + Math.min(String(category).length, 20) * 7 + 12, 0);
  return needed > 700 ? 45 : 0;
}

function paletteFor(options: any): string[] {
  const scheme = resolveColorScheme(options.color_scheme);
  // @ts-expect-error indexing a literal by a string
  return AllColorPaletteArrays[scheme];
}

function seriesColor(options: any, name: string, index: number): string {
  const overrides = options.seriesOptions[name] || {};
  if (overrides.color) {
    return overrides.color;
  }
  const palette = paletteFor(options);
  return palette[index % palette.length];
}

/** Collapse repeated x values, matching the aggregation the old renderer did. */
function aggregate(points: any[], xAxisType: string, seriesType: string, missingValuesAsZero: boolean) {
  const byX = new Map<any, any>();
  each(points, (point) => {
    const x = normalizeX(point.x, xAxisType);
    let y = cleanNumber(point.y);
    if (missingValuesAsZero && isNil(y)) {
      y = 0;
    }
    const aggregatable = !isNil(x) && ["column", "line", "area"].includes(seriesType);
    const yError = cleanNumber(point.yError);
    const existing = aggregatable ? byX.get(x) : undefined;
    if (existing) {
      existing.y = isNil(existing.y) ? y : (existing.y || 0) + (y || 0);
      // Errors add with the values they belong to, as they did before.
      if (!isNil(yError)) {
        existing.yError = isNil(existing.yError) ? yError : existing.yError + yError;
      }
      return;
    }
    byX.set(aggregatable ? x : Symbol("point"), {
      x,
      y,
      yError,
      // Carried through for bubble sizing and heatmap values; dropping them
      // here is why those two could not be built from this shape before.
      size: cleanNumber(point.size),
      zVal: cleanNumber(point.zVal),
      row: point.$raw,
    });
  });
  return Array.from(byX.values());
}

/** Percent stacking: ECharts has no normalized mode, so the maths happens here. */
function applyPercentValues(seriesData: any[][], options: any) {
  if (!options.series.percentValues) {
    return;
  }
  const totals = new Map<any, number>();
  each(seriesData, (points) =>
    each(points, (point) => {
      totals.set(point.x, (totals.get(point.x) || 0) + Math.abs(point.y || 0));
    })
  );
  each(seriesData, (points) =>
    each(points, (point) => {
      const total = totals.get(point.x);
      point.y = isNil(point.y) || !total ? null : (point.y / total) * 100;
    })
  );
}

function buildTooltipFormatter(options: any, horizontal: boolean) {
  const formatNumber = createNumberFormatter(options.numberFormat);
  const formatPercent = createNumberFormatter(options.percentFormat);
  // Pair data is [x, y] upright and [y, x] on its side, so the measure is not
  // always the second number.
  const valueIndex = horizontal ? 0 : 1;
  return (params: any) => {
    const items = Array.isArray(params) ? params : [params];
    return map(items, (item) => {
      const value = Array.isArray(item.value) ? item.value[valueIndex] : item.value;
      const context = {
        "@@name": item.seriesName,
        "@@x": item.axisValueLabel ?? item.name,
        "@@y": options.series.percentValues ? formatPercent(value) : formatNumber(value),
        "@@yPercent": formatPercent(value),
      };
      const text = options.textFormat ? formatSimpleTemplate(options.textFormat, context) : null;
      return text || `${item.marker} ${item.seriesName}: ${context["@@y"]}`;
    }).join("<br/>");
  };
}

/**
 * Bubble sizing.
 *
 * Plotly's `sizemode: "area"` treats the number as an area; ECharts' symbolSize
 * is a diameter. Without the conversion an area-mode chart renders bubbles
 * wildly too large, and the relative sizes are wrong as well as the absolute.
 */
function bubbleSymbolSize(options: any) {
  const coefficient = options.coefficient || 1;
  const byArea = options.sizemode === "area";
  return (value: any) => {
    const raw = Array.isArray(value) ? value[2] : null;
    const scaled = Math.max((cleanNumber(raw) || 0) * coefficient, 0);
    return byArea ? 2 * Math.sqrt(scaled / Math.PI) : scaled;
  };
}

function buildCartesianSeries(
  chartData: any[],
  options: any,
  xAxisType: string,
  categories: any[],
  horizontal: boolean
) {
  const stacking = options.series.stacking;
  const showLabels = options.showDataLabels;
  const formatNumber = createNumberFormatter(options.numberFormat);

  const prepared = map(chartData, (series) => {
    const overrides = extend({ type: options.globalSeriesType, yAxis: 0 }, options.seriesOptions[series.name]);
    const points = aggregate(series.data, xAxisType, overrides.type, options.missingValuesAsZero);
    return { series, overrides, points };
  });

  applyPercentValues(map(prepared, "points"), options);

  // Bars share the category band, so an error bar sitting at the category
  // centre would miss its bar whenever more than one series is drawn. Count the
  // bars first so each one knows its slot.
  const barCount = stacking ? 1 : filter(prepared, ({ overrides }) => overrides.type === "column").length;
  let barSlot = 0;

  // Stacked bars sit on top of each other, so the mark belongs at the running
  // total rather than at the series' own value.
  const stackTotals = new Map<any, number>();

  const errorBars: any[] = [];

  const built = map(prepared, ({ series, overrides, points }, index) => {
    const color = seriesColor(options, series.name, index);
    const isArea = overrides.type === "area";
    const isBubble = overrides.type === "bubble";
    const isScatterLike = isBubble || overrides.type === "scatter";
    const echartsType = overrides.type === "column" ? "bar" : isArea ? "line" : isBubble ? "scatter" : overrides.type;

    // Scatter and bubble keep their own x values: they are point clouds, not a
    // value per category, and bubbles carry a third number for the radius.
    // Everything else on a category axis is aligned to the shared category list
    // so a given array position means the same category in every series, which
    // is what makes stacking correct and animation meaningful.
    // On a category axis ECharts reads a bare value and takes the position from
    // the array index, so the same data works either way round. Pair data has
    // to be written in axis order -- [category, measure] upright, and the other
    // way when the chart is on its side. Swapping only the axes leaves the
    // pairs pointing the original way, which is why "horizontal" used to do
    // nothing but relabel the ticks.
    const pair = (a: any, b: any, extra?: any) =>
      extra === undefined ? (horizontal ? [b, a] : [a, b]) : horizontal ? [b, a, extra] : [a, b, extra];

    const byX = new Map(points.map((p: any) => [p.x, p.y]));
    const data = isScatterLike
      ? map(points, (p: any) => pair(p.x, p.y, p.size))
      : xAxisType === "category"
        ? map(categories, (category) => (byX.has(category) ? byX.get(category) : null))
        : map(points, (p: any) => pair(p.x, p.y));

    const built: any = {
      id: seriesId(series.name),
      name: overrides.name || series.name,
      type: echartsType,
      data,
      // The measure axis carries the series' axis assignment; on its side that
      // is the x axis, and there is only ever one category axis.
      ...(horizontal
        ? { xAxisIndex: getSeriesAxisIndex(series.name, options), yAxisIndex: 0 }
        : { yAxisIndex: getSeriesAxisIndex(series.name, options) }),
      itemStyle: { color },
      emphasis: { focus: "series" },
      // Performance: above these thresholds ECharts switches to a batched path
      // instead of one graphic element per point.
      large: true,
      largeThreshold: 400,
    };

    if (echartsType === "bar") {
      // Pinned, not defaulted: error bars are placed from these numbers.
      extend(built, BAR_LAYOUT);
    }
    if (isBubble) {
      built.symbolSize = bubbleSymbolSize(options);
    }
    if (isArea) {
      built.areaStyle = { opacity: 0.25 };
    }
    if (echartsType === "line") {
      built.showSymbol = points.length <= 200;
      built.smooth = options.lineShape === "spline";
      if (options.lineShape === "hv") {
        built.step = "end";
      }
      // Downsample long series for drawing only; the data itself is untouched.
      built.sampling = "lttb";
    }
    if (stacking && !isScatterLike) {
      built.stack = "total";
    }
    if (showLabels) {
      built.label = {
        show: true,
        position: isArea || echartsType === "line" ? "top" : "inside",
        formatter: (params: any) =>
          formatNumber(Array.isArray(params.value) ? params.value[horizontal ? 0 : 1] : params.value),
        // The number itself counts from the old value to the new one instead of
        // snapping. This is the "2 to 4 in motion" part.
        valueAnimation: true,
      };
    }

    const offset = overrides.type === "column" && !stacking ? barCentreOffset(barSlot++, barCount) : 0;
    const errorSeries = buildErrorBarSeries(
      built.id,
      built.name,
      map(points, (p: any) => {
        const base = stacking && !isNil(p.y) ? (stackTotals.get(p.x) || 0) + p.y : p.y;
        if (stacking && !isNil(p.y)) {
          stackTotals.set(p.x, base);
        }
        return { x: p.x, y: base, yError: p.yError };
      }),
      color,
      built.yAxisIndex,
      offset
    );
    if (errorSeries) {
      errorBars.push(errorSeries);
    }

    return built;
  });

  // Appended rather than interleaved so the bars they annotate are drawn first.
  return [...built, ...errorBars];
}

/** A box has five numbers rather than one, so it gets its own tooltip. */
function buildBoxTooltipFormatter(options: any) {
  const formatNumber = createNumberFormatter(options.numberFormat);
  const LABELS = ["Minimum", "Lower quartile", "Median", "Upper quartile", "Maximum"];
  return (params: any) => {
    const item = Array.isArray(params) ? params[0] : params;
    if (item.seriesType !== "boxplot") {
      return "";
    }
    // A boxplot item's value leads with the data index, then the five numbers.
    const stats = item.value.slice(item.value.length - 5);
    const rows = map(LABELS, (label, index) => `${label}: ${formatNumber(stats[index])}`).join("<br/>");
    return `${item.marker} ${item.seriesName} &middot; ${item.name}<br/>${rows}`;
  };
}

function buildPieSeries(chartData: any[], options: any) {
  const palette = paletteFor(options);
  return map(chartData, (series, seriesIndex) => ({
    id: seriesId(series.name),
    name: series.name,
    type: "pie",
    radius: chartData.length > 1 ? "55%" : "65%",
    center: chartData.length > 1 ? [`${((seriesIndex % 2) + 0.5) * 50}%`, "50%"] : ["50%", "50%"],
    data: map(series.data, (point: any, index: number) => ({
      name: String(point.x),
      value: cleanNumber(point.y),
      itemStyle: { color: (options.seriesOptions[point.x] || {}).color || palette[index % palette.length] },
    })),
    label: { show: options.showDataLabels !== false },
    emphasis: { focus: "self" },
  }));
}

function heatRamp(options: any): string[] {
  if (options.colorScheme === "Custom..." && options.heatMinColor && options.heatMaxColor) {
    return [options.heatMinColor, options.heatMaxColor];
  }
  // A saved visualization names a Plotly scale; keep that scale's colours
  // rather than quietly recolouring someone's chart on upgrade.
  return HEAT_RAMPS[options.colorScheme] || DEFAULT_HEAT_RAMP;
}

function buildHeatmap(chartData: any[], options: any) {
  const formatNumber = createNumberFormatter(options.numberFormat);
  const points = chartData.flatMap((series: any) => series.data);

  let xCategories = uniq(map(points, (p: any) => String(p.x)));
  let yCategories = uniq(map(points, (p: any) => String(p.y)));
  if (options.sortX) {
    xCategories = sortBy(xCategories);
  }
  if (options.sortY) {
    yCategories = sortBy(yCategories);
  }
  if (options.reverseX) {
    xCategories = xCategories.slice().reverse();
  }
  if (options.reverseY) {
    yCategories = yCategories.slice().reverse();
  }

  const data = map(points, (p: any) => [
    xCategories.indexOf(String(p.x)),
    yCategories.indexOf(String(p.y)),
    cleanNumber(p.zVal) || 0,
  ]);
  const zMax = max(map(data, (d: any) => d[2])) || 0;
  const ramp = heatRamp(options);

  const series = [
    {
      id: "series:heatmap",
      name: "heatmap",
      type: "heatmap",
      data,
      label: {
        show: !!options.showDataLabels,
        formatter: (params: any) => formatNumber(params.value[2]),
        // Keep labels legible against whichever end of the ramp they land on.
        color: chooseTextColorForBackground(ramp[ramp.length - 1]),
      },
      emphasis: { itemStyle: { borderColor: "#000", borderWidth: 1 } },
      progressive: 1000,
    },
  ];

  return { series, xCategories, yCategories, zMax, ramp };
}

export default function buildOption(chartData: any[], options: any): BuiltOption {
  const isPie = options.globalSeriesType === "pie";
  const isHeatmap = options.globalSeriesType === "heatmap";
  const horizontal = !!options.swappedAxes;

  if (isHeatmap) {
    const { series, xCategories, yCategories, zMax, ramp } = buildHeatmap(chartData, options);
    const categoryAxis = (data: any[]) => ({ type: "category", data, splitArea: { show: true } });
    const option: any = {
      animation: true,
      animationDuration: 300,
      animationDurationUpdate: 450,
      animationEasingUpdate: "cubicOut",
      grid: { left: 12, right: 12, top: 24, bottom: 60, containLabel: true },
      xAxis: categoryAxis(xCategories),
      yAxis: categoryAxis(yCategories),
      tooltip: {
        trigger: "item",
        confine: true,
        formatter: (params: any) =>
          `${xCategories[params.value[0]]} / ${yCategories[params.value[1]]}: ${params.value[2]}`,
      },
      visualMap: {
        min: 0,
        max: zMax,
        calculable: true,
        orient: "horizontal",
        left: "center",
        bottom: 0,
        inRange: { color: ramp },
      },
      series,
    };
    return {
      option,
      signature: JSON.stringify({ type: "heatmap", xCategories, yCategories }),
    };
  }

  // A rolling window trims the data before anything is measured from it, so
  // categories, axis ranges and statistics describe only what is shown.
  if (!isPie) {
    chartData = applyWindow(chartData, options.window);
  }

  const isBox = options.globalSeriesType === "box";
  const hasBars =
    !isPie &&
    !isBox &&
    some(chartData, (dataSeries: any) => {
      const type = (options.seriesOptions[dataSeries.name] || {}).type || options.globalSeriesType;
      return type === "column";
    });

  const allX = isPie ? [] : chartData.flatMap((series: any) => map(series.data, "x"));
  // A box groups every row sharing an x into one distribution, so its x is a
  // category however the values are typed -- numeric bin labels included.
  const detectedAxisType = isPie ? "category" : echartsAxisType(options.xAxis.type, allX);

  // A bar is a discrete thing, not a position on a continuum, and it gets a
  // category axis for two reasons. ECharts takes a bar's direction from which
  // axis is the category one, so with two value axes it draws bars upright
  // whatever the data says -- a numeric-x chart simply refused to lie down.
  // And a value axis puts its ticks at round numbers rather than at the bars,
  // so most bars had no label of their own.
  //
  // Time is the exception: a gap between two dates means no data on the days
  // between, and collapsing that into evenly spaced categories would draw a
  // month of readings as if they were consecutive.
  const barsWantCategories = hasBars && detectedAxisType !== "time";
  const xAxisType = isPie || isBox || barsWantCategories ? "category" : detectedAxisType;

  let categories: any[] = [];
  if (!isPie && xAxisType === "category") {
    const seen = new Set<any>();
    each(chartData, (series: any) =>
      each(series.data, (point: any) => {
        const x = normalizeX(point.x, xAxisType);
        if (!isNil(x)) {
          seen.add(x);
        }
      })
    );
    categories = Array.from(seen);
    if (options.sortX) {
      categories = sortBy(categories);
    }
    if (options.reverseX) {
      categories = categories.reverse();
    }
  }

  const series = isPie
    ? buildPieSeries(chartData, options)
    : isBox
      ? buildBoxSeries(chartData, options, xAxisType, categories, (name, index) => seriesColor(options, name, index))
      : buildCartesianSeries(chartData, options, xAxisType, categories, horizontal);

  const valueAxis = (axisOptions: any) => ({
    type: echartsAxisType(axisOptions.type) === "category" ? "value" : echartsAxisType(axisOptions.type),
    name: axisOptions.title ? axisOptions.title.text || axisOptions.title : undefined,
    nameLocation: "middle",
    nameGap: 36,
    axisLabel: { formatter: createNumberFormatter(options.numberFormat) },
    scale: !options.series.stacking && !hasBars,
  });

  const categoryAxis = {
    type: xAxisType,
    data: xAxisType === "category" ? categories : undefined,
    name: options.xAxis.title ? options.xAxis.title.text || options.xAxis.title : undefined,
    nameLocation: "middle",
    nameGap: 30,
    axisLabel: {
      show: options.xAxis.labels ? options.xAxis.labels.enabled : true,
      // Every bar gets its own label. ECharts' default drops whichever ones
      // would collide, which on a bar chart means bars with no label at all;
      // tilting is the answer instead, and `containLabel` reserves the room.
      // Sideways, the labels stack down the axis and never need tilting.
      ...(barsWantCategories && categories.length <= MAX_LABELLED_CATEGORIES
        ? { interval: 0, hideOverlap: false, rotate: horizontal ? 0 : categoryLabelRotation(categories) }
        : { hideOverlap: true }),
      formatter: (value: any) => {
        const text = String(value);
        return text.length > AXIS_LABEL_LIMIT ? `${text.slice(0, AXIS_LABEL_LIMIT)}…` : text;
      },
    },
  };

  const option: any = {
    animation: true,
    animationDuration: 300,
    // The update animation is the whole point: when new data arrives for the
    // same series and categories, ECharts tweens from the old values.
    animationDurationUpdate: 450,
    animationEasingUpdate: "cubicOut",
    color: paletteFor(options),
    legend: {
      show: options.legend.enabled,
      type: "scroll",
      bottom: 0,
      icon: "roundRect",
    },
    tooltip: {
      trigger: isPie || isBox ? "item" : "axis",
      axisPointer: { type: options.globalSeriesType === "column" ? "shadow" : "line" },
      confine: true,
      formatter: isBox ? buildBoxTooltipFormatter(options) : buildTooltipFormatter(options, horizontal),
    },
    series,
  };

  if (!isPie) {
    const zoom = zoomComponents(options.zoom, horizontal);
    const slider = !!zoom && zoom.some((z) => z.type === "slider");
    option.grid = {
      left: 12,
      right: horizontal && slider ? 40 : 12,
      top: 24,
      // Room for the legend, and for a zoom slider under the axis.
      bottom: (options.legend.enabled ? 36 : 12) + (slider && !horizontal ? 30 : 0),
      containLabel: true,
    };
    if (zoom) {
      // The slider sits between the axis and the legend.
      option.dataZoom = zoom.map((z) =>
        z.type === "slider" && !horizontal ? { ...z, bottom: options.legend.enabled ? 30 : 6 } : z
      );
    }
    const measureAxes = (secondPosition: string) => [
      valueAxis(options.yAxis[0]),
      { ...valueAxis(options.yAxis[1] || options.yAxis[0]), position: secondPosition },
    ];
    // Two measure axes either way: a series assigned to the second one needs an
    // axis to sit on whichever way round the chart is drawn.
    option.xAxis = horizontal ? measureAxes("top") : categoryAxis;
    option.yAxis = horizontal ? [categoryAxis] : measureAxes("right");
  }

  if (!isPie) {
    addReferences(option, options, horizontal);
  }

  const signature = JSON.stringify({
    type: options.globalSeriesType,
    horizontal,
    xAxisType,
    categories,
    ids: map(option.series, "id"),
    zoom: options.zoom || "none",
  });

  return { option, signature };
}
