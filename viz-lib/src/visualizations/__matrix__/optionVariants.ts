/*
  Every option each visualization offers, and the values it can take.

  The editor lets people combine these freely, so this is the surface that has
  to hold up -- not the default each visualization was written against. The
  point of listing them here rather than in each visualization's own test is
  that the matrix then covers options nobody thought to combine.
*/

export interface Variant {
  name: string;
  options: any;
}

const FORMATS = [
  { style: "auto", decimals: null },
  { style: "number", decimals: 2 },
  { style: "compact", decimals: 1 },
  { style: "percent", decimals: 0 },
  { style: "currency", decimals: 2, currency: "EUR" },
  { style: "bytes", decimals: 1 },
  { style: "duration", decimals: 0 },
  { style: "number", decimals: 0, prefix: "~", suffix: " ms" },
];

/** The same format sweep, applied to whichever option holds one. */
function formatVariants(key: string, base: any = {}): Variant[] {
  return FORMATS.map((valueFormat) => ({
    name: `${key} as ${valueFormat.style}${valueFormat.prefix ? " with affixes" : ""}`,
    options: { ...base, [key]: valueFormat },
  }));
}

const THRESHOLDS = [
  { name: "no thresholds", options: { thresholds: { base: "", steps: [] } } },
  { name: "a base colour only", options: { thresholds: { base: "good", steps: [] } } },
  {
    name: "three steps",
    options: {
      thresholds: {
        base: "good",
        steps: [
          { value: 30, color: "warning" },
          { value: 60, color: "critical" },
        ],
      },
    },
  },
  // Steps out of order, which the editor allows and people do.
  {
    name: "steps out of order",
    options: {
      thresholds: {
        base: "good",
        steps: [
          { value: 90, color: "critical" },
          { value: 10, color: "warning" },
        ],
      },
    },
  },
  { name: "a step with no colour", options: { thresholds: { base: "good", steps: [{ value: 50, color: "" }] } } },
];

export const VARIANTS: Record<string, Variant[]> = {
  COUNTER: [
    { name: "defaults", options: {} },
    { name: "classic formatting", options: { formatMode: "classic", stringDecimal: 2, stringThouSep: " " } },
    { name: "a named column and label", options: { counterColName: "value", counterLabel: "Revenue" } },
    { name: "the last row", options: { counterColName: "value", rowNumber: -1 } },
    { name: "a row past the end", options: { counterColName: "value", rowNumber: 99 } },
    { name: "row zero", options: { counterColName: "value", rowNumber: 0 } },
    { name: "a target column", options: { counterColName: "value", targetColName: "target" } },
    { name: "a sparkline", options: { counterColName: "value", sparkline: { enabled: true, timeColumn: "started" } } },
    {
      name: "a sparkline with no time column",
      options: { counterColName: "value", sparkline: { enabled: true, timeColumn: "" } },
    },
    {
      name: "compared with the previous row",
      options: { counterColName: "value", comparison: { mode: "previous", rowsBack: 1, display: "percent" } },
    },
    {
      name: "compared with a target",
      options: {
        counterColName: "value",
        targetColName: "target",
        comparison: { mode: "target", display: "absolute" },
      },
    },
    {
      name: "compared several rows back",
      options: { counterColName: "value", comparison: { mode: "previous", rowsBack: 5, display: "percent" } },
    },
    { name: "a missing column", options: { counterColName: "not_a_column" } },
    ...THRESHOLDS.map((t) => ({ name: `stat, ${t.name}`, options: { counterColName: "value", ...t.options } })),
    ...formatVariants("valueFormat", { counterColName: "value", formatMode: "value" }),
  ],

  GAUGE: [
    ...["needle", "half", "ring"].map((style) => ({
      name: `the ${style} style`,
      options: { valueColumn: "value", style },
    })),
    { name: "a label", options: { valueColumn: "value", label: "CPU" } },
    { name: "a target", options: { valueColumn: "value", target: 60 } },
    { name: "a target column", options: { valueColumn: "value", targetColumn: "target" } },
    { name: "a target past the maximum", options: { valueColumn: "value", target: 1e6 } },
    { name: "min and max from columns", options: { valueColumn: "value", minColumn: "other", maxColumn: "target" } },
    { name: "an inverted range", options: { valueColumn: "value", min: 100, max: 0 } },
    { name: "a range of nothing", options: { valueColumn: "value", min: 50, max: 50 } },
    { name: "a negative range", options: { valueColumn: "value", min: -100, max: -10 } },
    { name: "a huge range", options: { valueColumn: "value", min: 0, max: 1e9 } },
    { name: "the last row", options: { valueColumn: "value", rowNumber: -1 } },
    { name: "a missing column", options: { valueColumn: "not_a_column" } },
    ...THRESHOLDS.map((t) => ({ name: `gauge, ${t.name}`, options: { valueColumn: "value", ...t.options } })),
    ...formatVariants("valueFormat", { valueColumn: "value" }),
  ],

  PROGRESS: [
    ...["bullet", "bar"].map((mode) => ({ name: `the ${mode} style`, options: { valueColumn: "value", mode } })),
    { name: "no label column", options: { valueColumn: "value", labelColumn: "" } },
    { name: "a target column", options: { valueColumn: "value", targetColumn: "target" } },
    { name: "one target for every row", options: { valueColumn: "value", target: 50 } },
    { name: "a fixed maximum", options: { valueColumn: "value", max: 500 } },
    { name: "a maximum below the values", options: { valueColumn: "value", max: 1 } },
    { name: "a target of zero", options: { valueColumn: "value", target: 0 } },
    { name: "a missing column", options: { valueColumn: "not_a_column" } },
    ...THRESHOLDS.map((t) => ({ name: `progress, ${t.name}`, options: { valueColumn: "value", ...t.options } })),
    ...formatVariants("valueFormat", { valueColumn: "value" }),
  ],

  HISTOGRAM: [
    { name: "bins chosen from the data", options: { valueColumn: "value", binCount: null } },
    ...[1, 2, 7, 30, 250, 10000].map((binCount) => ({
      name: `${binCount} bins`,
      options: { valueColumn: "value", binCount },
    })),
    { name: "a nonsense bin count", options: { valueColumn: "value", binCount: -4 } },
    ...["count", "percent"].map((countMode) => ({
      name: `bars as ${countMode}`,
      options: { valueColumn: "value", countMode },
    })),
    { name: "with the mean", options: { valueColumn: "value", showMean: true } },
    { name: "a named colour", options: { valueColumn: "value", color: "critical" } },
    { name: "a literal colour", options: { valueColumn: "value", color: "#ff00aa" } },
    { name: "a text column", options: { valueColumn: "label" } },
    { name: "a missing column", options: { valueColumn: "not_a_column" } },
    ...formatVariants("valueFormat", { valueColumn: "value" }),
  ],

  WATERFALL: [
    { name: "defaults", options: { labelColumn: "label", valueColumn: "value" } },
    { name: "no total", options: { labelColumn: "label", valueColumn: "value", showTotal: false } },
    { name: "a renamed total", options: { labelColumn: "label", valueColumn: "value", totalLabel: "Net" } },
    { name: "subtotals", options: { labelColumn: "label", valueColumn: "value", totalColumn: "status" } },
    { name: "no labels on the bars", options: { labelColumn: "label", valueColumn: "value", showValues: false } },
    { name: "no connectors", options: { labelColumn: "label", valueColumn: "value", showConnectors: false } },
    { name: "numbered steps", options: { labelColumn: "", valueColumn: "value" } },
    {
      name: "recoloured",
      options: {
        labelColumn: "label",
        valueColumn: "value",
        riseColor: "accent",
        fallColor: "#333",
        totalColor: "warning",
      },
    },
    { name: "a missing column", options: { labelColumn: "label", valueColumn: "not_a_column" } },
    ...formatVariants("valueFormat", { labelColumn: "label", valueColumn: "value" }),
  ],

  RADAR: [
    { name: "defaults", options: {} },
    { name: "three measures", options: { labelColumn: "label", valueColumns: ["value", "other", "target"] } },
    { name: "two measures, too few", options: { labelColumn: "label", valueColumns: ["value", "other"] } },
    { name: "one measure", options: { labelColumn: "label", valueColumns: ["value"] } },
    ...["per-spoke", "shared"].map((scaleMode) => ({
      name: `${scaleMode} scales`,
      options: { labelColumn: "label", valueColumns: ["value", "other", "target"], scaleMode },
    })),
    ...["polygon", "circle"].map((shape) => ({
      name: `a ${shape} web`,
      options: { labelColumn: "label", valueColumns: ["value", "other", "target"], shape },
    })),
    {
      name: "unfilled",
      options: { labelColumn: "label", valueColumns: ["value", "other", "target"], showArea: false },
    },
    {
      name: "no legend",
      options: { labelColumn: "label", valueColumns: ["value", "other", "target"], showLegend: false },
    },
    { name: "numbered rows", options: { labelColumn: "", valueColumns: ["value", "other", "target"] } },
    { name: "missing measures", options: { labelColumn: "label", valueColumns: ["gone", "also_gone", "missing"] } },
    ...formatVariants("valueFormat", { labelColumn: "label", valueColumns: ["value", "other", "target"] }),
  ],

  TREEMAP: [
    { name: "one level", options: { pathColumns: ["label"], valueColumn: "value" } },
    { name: "two levels", options: { pathColumns: ["label", "status"], valueColumn: "value" } },
    { name: "three levels", options: { pathColumns: ["label", "status", "other"], valueColumn: "value" } },
    ...[1, 2, 3, 4].map((visibleDepth) => ({
      name: `${visibleDepth} levels at once`,
      options: { pathColumns: ["label", "status"], valueColumn: "value", visibleDepth },
    })),
    { name: "a silly depth", options: { pathColumns: ["label"], valueColumn: "value", visibleDepth: 99 } },
    { name: "with values written", options: { pathColumns: ["label"], valueColumn: "value", showValues: true } },
    {
      name: "no breadcrumb",
      options: { pathColumns: ["label", "status"], valueColumn: "value", showBreadcrumb: false },
    },
    { name: "no grouping column", options: { pathColumns: [], valueColumn: "value" } },
    { name: "a missing size column", options: { pathColumns: ["label"], valueColumn: "not_a_column" } },
    ...formatVariants("valueFormat", { pathColumns: ["label"], valueColumn: "value" }),
  ],

  CALENDAR_HEATMAP: [
    ...["3-months", "12-months", "year", "all"].map((range) => ({
      name: `showing ${range}`,
      options: { dateColumn: "started", valueColumn: "value", range },
    })),
    { name: "an unknown range", options: { dateColumn: "started", valueColumn: "value", range: "fortnight" } },
    { name: "counting rows", options: { dateColumn: "started", valueColumn: "" } },
    { name: "weeks from Sunday", options: { dateColumn: "started", valueColumn: "value", startOnMonday: false } },
    { name: "a named colour", options: { dateColumn: "started", valueColumn: "value", color: "critical" } },
    { name: "a text column as the date", options: { dateColumn: "label", valueColumn: "value" } },
    { name: "a missing date column", options: { dateColumn: "not_a_column", valueColumn: "value" } },
    ...formatVariants("valueFormat", { dateColumn: "started", valueColumn: "value" }),
  ],

  STATE_TIMELINE: [
    {
      name: "start and end",
      options: { laneColumn: "label", startColumn: "started", endColumn: "ended", stateColumn: "status" },
    },
    {
      name: "a duration instead",
      options: { laneColumn: "label", startColumn: "started", endColumn: "", durationColumn: "other" },
    },
    {
      name: "neither end nor duration",
      options: { laneColumn: "label", startColumn: "started", endColumn: "", durationColumn: "" },
    },
    {
      name: "one track",
      options: { laneColumn: "", startColumn: "started", endColumn: "ended", stateColumn: "status" },
    },
    {
      name: "no state column",
      options: { laneColumn: "label", startColumn: "started", endColumn: "ended", stateColumn: "" },
    },
    {
      name: "labels on the bars",
      options: {
        laneColumn: "label",
        startColumn: "started",
        endColumn: "ended",
        stateColumn: "status",
        showLabels: true,
      },
    },
    {
      name: "a custom time format",
      options: { laneColumn: "label", startColumn: "started", endColumn: "ended", timeFormat: "HH:mm:ss" },
    },
    {
      name: "an empty time format",
      options: { laneColumn: "label", startColumn: "started", endColumn: "ended", timeFormat: "" },
    },
    {
      name: "no mappings",
      options: { laneColumn: "label", startColumn: "started", endColumn: "ended", stateColumn: "status", mappings: [] },
    },
    {
      name: "renamed states",
      options: {
        laneColumn: "label",
        startColumn: "started",
        endColumn: "ended",
        stateColumn: "status",
        mappings: [{ value: "down", text: "Outage", color: "critical" }],
      },
    },
    { name: "a missing start column", options: { laneColumn: "label", startColumn: "not_a_column" } },
    { name: "a text column as the start", options: { laneColumn: "label", startColumn: "label" } },
  ],

  STATUS_GRID: [
    { name: "defaults", options: { nameColumn: "label", valueColumn: "value" } },
    { name: "a status column", options: { nameColumn: "label", valueColumn: "value", statusColumn: "status" } },
    { name: "a detail column", options: { nameColumn: "label", valueColumn: "value", detailColumn: "status" } },
    ...["small", "medium", "large"].map((tileSize) => ({
      name: `${tileSize} tiles`,
      options: { nameColumn: "label", valueColumn: "value", tileSize },
    })),
    ...["none", "name", "value", "severity"].map((sort) => ({
      name: `sorted by ${sort}`,
      options: { nameColumn: "label", valueColumn: "value", sort },
    })),
    {
      name: "no mappings",
      options: { nameColumn: "label", valueColumn: "value", statusColumn: "status", mappings: [] },
    },
    { name: "a missing column", options: { nameColumn: "label", valueColumn: "not_a_column" } },
    ...THRESHOLDS.map((t) => ({
      name: `grid, ${t.name}`,
      options: { nameColumn: "label", valueColumn: "value", ...t.options },
    })),
    ...formatVariants("valueFormat", { nameColumn: "label", valueColumn: "value" }),
  ],

  FUNNEL: [
    ...["bars", "funnel"].map((shape) => ({
      name: `the ${shape} shape`,
      options: { shape, stepCol: { colName: "label" }, valueCol: { colName: "value" } },
    })),
    {
      name: "unsorted",
      options: { shape: "funnel", stepCol: { colName: "label" }, valueCol: { colName: "value" }, autoSort: false },
    },
    {
      name: "sorted by another column",
      options: {
        shape: "funnel",
        stepCol: { colName: "label" },
        valueCol: { colName: "value" },
        autoSort: false,
        sortKeyCol: { colName: "other", reverse: true },
      },
    },
    {
      name: "a tight limit",
      options: { shape: "funnel", stepCol: { colName: "label" }, valueCol: { colName: "value" }, itemsLimit: 2 },
    },
    { name: "no columns chosen", options: { shape: "funnel" } },
    {
      name: "a missing column",
      options: { shape: "funnel", stepCol: { colName: "label" }, valueCol: { colName: "not_a_column" } },
    },
  ],

  BOXPLOT: [{ name: "defaults", options: {} }],
  SANKEY: [{ name: "defaults", options: {} }],
  SUNBURST_SEQUENCE: [{ name: "defaults", options: {} }],
  DETAILS: [{ name: "defaults", options: {} }],
  TABLE: [
    { name: "defaults", options: {} },
    { name: "a small page", options: { itemsPerPage: 2 } },
    { name: "a huge page", options: { itemsPerPage: 1000 } },
  ],
  PIVOT: [
    { name: "defaults", options: {} },
    { name: "controls hidden", options: { controls: { enabled: true } } },
    { name: "no totals", options: { rendererOptions: { table: { colTotals: false, rowTotals: false } } } },
  ],
  WORD_CLOUD: [
    { name: "defaults", options: {} },
    { name: "a column", options: { column: "label" } },
    { name: "with frequencies", options: { column: "label", frequenciesColumn: "value" } },
    { name: "length limits", options: { column: "label", wordLengthLimit: { min: 2, max: 8 } } },
    { name: "count limits", options: { column: "label", wordCountLimit: { min: 1, max: 3 } } },
    { name: "impossible limits", options: { column: "label", wordLengthLimit: { min: 50, max: 2 } } },
    { name: "a missing column", options: { column: "not_a_column" } },
  ],
  COHORT: [
    { name: "defaults", options: {} },
    ...["daily", "weekly", "monthly"].map((timeInterval) => ({
      name: `${timeInterval} cohorts`,
      options: { timeInterval },
    })),
    ...["diagonal", "simple"].map((mode) => ({ name: `the ${mode} mode`, options: { mode } })),
    { name: "absolute values", options: { percentValues: false } },
  ],
  MAP: [
    { name: "defaults", options: {} },
    { name: "clustered", options: { clusterMarkers: true } },
    { name: "unclustered", options: { clusterMarkers: false } },
    { name: "custom markers", options: { customizeMarkers: true, iconShape: "doughnut" } },
  ],
  CHOROPLETH: [
    { name: "defaults", options: {} },
    ...["countries", "usa", "subdiv_japan"].map((mapType) => ({ name: `the ${mapType} map`, options: { mapType } })),
    ...["e", "q", "k"].map((clusteringMode) => ({ name: `${clusteringMode} clustering`, options: { clusteringMode } })),
    { name: "no legend", options: { legend: { visible: false } } },
  ],

  CHART: [
    ...["line", "column", "bar", "area", "scatter", "bubble", "pie", "heatmap", "box"].map((globalSeriesType) => ({
      name: `a ${globalSeriesType} chart`,
      options: { globalSeriesType, columnMapping: { label: "x", value: "y" } },
    })),
    {
      name: "a rose",
      options: { globalSeriesType: "pie", pieStyle: "rose", columnMapping: { label: "x", value: "y" } },
    },
    {
      name: "two series",
      options: { globalSeriesType: "line", columnMapping: { label: "x", value: "y", other: "y" } },
    },
    {
      name: "a grouping column",
      options: { globalSeriesType: "line", columnMapping: { started: "x", value: "y", label: "series" } },
    },
    ...["stack", null].map((stacking) => ({
      name: `stacking: ${stacking}`,
      options: {
        globalSeriesType: "column",
        series: { stacking },
        columnMapping: { label: "x", value: "y", other: "y" },
      },
    })),
    {
      name: "percent values",
      options: {
        globalSeriesType: "column",
        series: { stacking: "stack", percentValues: true },
        columnMapping: { label: "x", value: "y", other: "y" },
      },
    },
    {
      name: "the legend below",
      options: {
        globalSeriesType: "line",
        legend: { enabled: true, placement: "below" },
        columnMapping: { label: "x", value: "y" },
      },
    },
    {
      name: "no legend",
      options: { globalSeriesType: "line", legend: { enabled: false }, columnMapping: { label: "x", value: "y" } },
    },
    {
      name: "a log y axis",
      options: {
        globalSeriesType: "line",
        yAxis: [{ type: "logarithmic" }],
        columnMapping: { label: "x", value: "y" },
      },
    },
    {
      name: "a category x axis",
      options: { globalSeriesType: "line", xAxis: { type: "category" }, columnMapping: { label: "x", value: "y" } },
    },
    {
      name: "a time x axis",
      options: { globalSeriesType: "line", xAxis: { type: "datetime" }, columnMapping: { started: "x", value: "y" } },
    },
    {
      name: "x labels hidden",
      options: {
        globalSeriesType: "column",
        xAxis: { labels: { enabled: false } },
        columnMapping: { label: "x", value: "y" },
      },
    },
    {
      name: "unsorted",
      options: { globalSeriesType: "line", sortX: false, columnMapping: { label: "x", value: "y" } },
    },
    {
      name: "missing values as zero",
      options: { globalSeriesType: "line", missingValuesAsZero: true, columnMapping: { label: "x", value: "y" } },
    },
    {
      name: "missing values left out",
      options: { globalSeriesType: "line", missingValuesAsZero: false, columnMapping: { label: "x", value: "y" } },
    },
    {
      name: "data labels",
      options: { globalSeriesType: "column", showDataLabels: true, columnMapping: { label: "x", value: "y" } },
    },
    {
      name: "a reference line",
      options: {
        globalSeriesType: "line",
        referenceLines: [{ type: "value", value: 50, label: "goal", color: "critical" }],
        columnMapping: { label: "x", value: "y" },
      },
    },
    {
      name: "a reference band",
      options: {
        globalSeriesType: "line",
        referenceBands: [{ from: 10, to: 40, color: "good" }],
        columnMapping: { label: "x", value: "y" },
      },
    },
    {
      name: "an average reference",
      options: {
        globalSeriesType: "line",
        referenceLines: [{ type: "average", series: "value" }],
        columnMapping: { label: "x", value: "y" },
      },
    },
    ...["none", "x", "slider"].map((zoom) => ({
      name: `zoom: ${zoom}`,
      options: { globalSeriesType: "line", zoom, columnMapping: { label: "x", value: "y" } },
    })),
    {
      name: "a rolling window of points",
      options: {
        globalSeriesType: "line",
        window: { mode: "points", points: 3 },
        columnMapping: { started: "x", value: "y" },
      },
    },
    {
      name: "a rolling window of minutes",
      options: {
        globalSeriesType: "line",
        window: { mode: "minutes", minutes: 30 },
        columnMapping: { started: "x", value: "y" },
      },
    },
    {
      name: "error bars",
      options: { globalSeriesType: "line", columnMapping: { label: "x", value: "y", other: "yError" } },
    },
    {
      name: "a bubble size column",
      options: { globalSeriesType: "bubble", columnMapping: { label: "x", value: "y", other: "size" } },
    },
    { name: "no mapping at all", options: { globalSeriesType: "line", columnMapping: {} } },
    {
      name: "a mapping to a missing column",
      options: { globalSeriesType: "line", columnMapping: { not_a_column: "x", value: "y" } },
    },
    ...["SQLDesk", "Viridis", "Tableau 10", "D3 Category 10", "Redash", "Not A Palette"].map((color_scheme) => ({
      name: `the ${color_scheme} palette`,
      options: { globalSeriesType: "column", color_scheme, columnMapping: { label: "x", value: "y" } },
    })),
  ],
};
