import { find, flatten, each } from "lodash";
import PropTypes from "prop-types";

import boxPlotVisualization from "./box-plot";
import chartVisualization from "./chart";
import choroplethVisualization from "./choropleth";
import cohortVisualization from "./cohort";
import counterVisualization from "./counter";
import detailsVisualization from "./details";
import funnelVisualization from "./funnel";
import gaugeVisualization from "./gauge";
import mapVisualization from "./map";
import pivotVisualization from "./pivot";
import progressVisualization from "./progress";
import sankeyVisualization from "./sankey";
import statusGridVisualization from "./status-grid";
import sunburstVisualization from "./sunburst";
import tableVisualization from "./table";
import wordCloudVisualization from "./word-cloud";

/**
 * What every visualization brings to the registry.
 *
 * Everything here is cheap and loads with the app: a name to put in a menu, a
 * size for the dashboard grid, and `getOptions`, which is option merging and
 * nothing more. The drawing code -- the Renderer and the Editor, and behind
 * them ECharts, Leaflet, a pivot table -- sits behind `load`, so a page pays
 * for a visualization only once it actually shows one.
 */
export type VisualizationComponents = {
  Renderer: (...args: any[]) => any;
  Editor?: (...args: any[]) => any;
};

type VisualizationConfig = {
  type: string;
  name: string;
  getOptions: (...args: any[]) => any;
  load: () => Promise<VisualizationComponents>;
  isDefault?: boolean;
  isDeprecated?: boolean;
  autoHeight?: boolean;
  defaultRows?: number;
  defaultColumns?: number;
  minRows?: number;
  maxRows?: number;
  minColumns?: number;
  maxColumns?: number;
};

// @ts-expect-error ts-migrate(2322) FIXME: Type 'Requireable<InferProps<{ type: Validator<str... Remove this comment to see the full error message
const VisualizationConfig: PropTypes.Requireable<VisualizationConfig> = PropTypes.shape({
  type: PropTypes.string.isRequired,
  name: PropTypes.string.isRequired,
  getOptions: PropTypes.func.isRequired,
  load: PropTypes.func.isRequired,
  isDefault: PropTypes.bool,
  isDeprecated: PropTypes.bool,
  // other config options
  autoHeight: PropTypes.bool,
  defaultRows: PropTypes.number,
  defaultColumns: PropTypes.number,
  minRows: PropTypes.number,
  maxRows: PropTypes.number,
  minColumns: PropTypes.number,
  maxColumns: PropTypes.number,
});

const registeredVisualizations = {};

function validateVisualizationConfig(config: any) {
  const typeSpecs = { config: VisualizationConfig };
  const values = { config };
  PropTypes.checkPropTypes(typeSpecs, values, "prop", "registerVisualization");
}

function registerVisualization(config: any) {
  validateVisualizationConfig(config);
  config = {
    ...config,
    isDefault: config.isDefault && !config.isDeprecated,
  };

  // @ts-expect-error ts-migrate(7053) FIXME: Element implicitly has an 'any' type because expre... Remove this comment to see the full error message
  if (registeredVisualizations[config.type]) {
    throw new Error(`Visualization ${config.type} already registered.`);
  }

  // @ts-expect-error ts-migrate(7053) FIXME: Element implicitly has an 'any' type because expre... Remove this comment to see the full error message
  registeredVisualizations[config.type] = config;
}

each(
  flatten([
    boxPlotVisualization,
    chartVisualization,
    choroplethVisualization,
    cohortVisualization,
    counterVisualization,
    detailsVisualization,
    funnelVisualization,
    gaugeVisualization,
    mapVisualization,
    pivotVisualization,
    progressVisualization,
    sankeyVisualization,
    statusGridVisualization,
    sunburstVisualization,
    tableVisualization,
    wordCloudVisualization,
  ]),
  registerVisualization
);

export default registeredVisualizations;

/**
 * Modules already fetched, so a visualization that has been drawn once can be
 * drawn again without suspending -- and so `loadVisualization` is safe to call
 * as often as you like.
 */
const loaded = new Map<string, VisualizationComponents>();
const loading = new Map<string, Promise<VisualizationComponents>>();

/** The components for a type, fetching them if this is the first time. */
export function loadVisualization(type: string): Promise<VisualizationComponents> {
  const ready = loaded.get(type);
  if (ready) {
    return Promise.resolve(ready);
  }
  const inFlight = loading.get(type);
  if (inFlight) {
    return inFlight;
  }
  // @ts-expect-error ts-migrate(7053) FIXME: Element implicitly has an 'any' type because expre... Remove this comment to see the full error message
  const config = registeredVisualizations[type];
  if (!config) {
    return Promise.reject(new Error(`Visualization ${type} is not registered.`));
  }
  const promise = config.load().then((components: VisualizationComponents) => {
    loaded.set(type, components);
    loading.delete(type);
    return components;
  });
  // A failed fetch is not remembered: a chunk that 404s because a deploy landed
  // mid-session may well be there on the next try.
  promise.catch(() => loading.delete(type));
  loading.set(type, promise);
  return promise;
}

/**
 * Start fetching a visualization before anything needs to draw it.
 *
 * A dashboard knows which types it holds well before its data arrives, and the
 * fetch costs nothing if it turns out to be unnecessary.
 */
export function preloadVisualization(type: string): void {
  if (type) {
    loadVisualization(type).catch(() => {});
  }
}

export function getDefaultVisualization() {
  // return any visualization explicitly marked as default, or any non-deprecated otherwise
  return (
    find(registeredVisualizations, (visualization: any) => visualization.isDefault) ||
    find(registeredVisualizations, (visualization: any) => !visualization.isDeprecated)
  );
}

export function newVisualization(type = null, options = {}) {
  const visualization: any = type ? registeredVisualizations[type] : getDefaultVisualization();
  return {
    type: visualization.type,
    name: visualization.name,
    description: "",
    options,
  };
}
