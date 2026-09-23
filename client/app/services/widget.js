import moment from "moment";
import { axios } from "@/services/axios";
import {
  each,
  pick,
  extend,
  isObject,
  truncate,
  keys,
  difference,
  filter,
  map,
  merge,
  sortBy,
  indexOf,
  size,
  includes,
} from "lodash";
import location from "@/services/location";
import { cloneParameter } from "@/services/parameters";
import dashboardGridOptions from "@/config/dashboard-grid-options";
import { registeredVisualizations, preloadVisualization } from "@sqldesk/viz/lib";
import shareInFlight from "./inFlightResults";
import { onPageLoad } from "./freshness";
import { Query } from "./query";
import QueryResult from "./query-result";

export const WidgetTypeEnum = {
  TEXTBOX: "textbox",
  VISUALIZATION: "visualization",
  RESTRICTED: "restricted",
};

function calculatePositionOptions(widget) {
  widget.width = 1; // Backward compatibility, user on back-end

  const visualizationOptions = {
    autoHeight: false,
    sizeX: Math.round(dashboardGridOptions.columns / 2),
    sizeY: dashboardGridOptions.defaultSizeY,
    minSizeX: dashboardGridOptions.minSizeX,
    maxSizeX: dashboardGridOptions.maxSizeX,
    minSizeY: dashboardGridOptions.minSizeY,
    maxSizeY: dashboardGridOptions.maxSizeY,
  };

  const config = widget.visualization ? registeredVisualizations[widget.visualization.type] : null;
  if (isObject(config)) {
    if (Object.prototype.hasOwnProperty.call(config, "autoHeight")) {
      visualizationOptions.autoHeight = config.autoHeight;
    }

    // Width constraints
    const minColumns = parseInt(config.minColumns, 10);
    if (isFinite(minColumns) && minColumns >= 0) {
      visualizationOptions.minSizeX = minColumns;
    }
    const maxColumns = parseInt(config.maxColumns, 10);
    if (isFinite(maxColumns) && maxColumns >= 0) {
      visualizationOptions.maxSizeX = Math.min(maxColumns, dashboardGridOptions.columns);
    }

    // Height constraints
    // `minRows` is preferred, but it should be kept for backward compatibility
    const height = parseInt(config.height, 10);
    if (isFinite(height)) {
      visualizationOptions.minSizeY = Math.ceil(height / dashboardGridOptions.rowHeight);
    }
    const minRows = parseInt(config.minRows, 10);
    if (isFinite(minRows)) {
      visualizationOptions.minSizeY = minRows;
    }
    const maxRows = parseInt(config.maxRows, 10);
    if (isFinite(maxRows) && maxRows >= 0) {
      visualizationOptions.maxSizeY = maxRows;
    }

    // Default dimensions
    const defaultWidth = parseInt(config.defaultColumns, 10);
    if (isFinite(defaultWidth) && defaultWidth > 0) {
      visualizationOptions.sizeX = defaultWidth;
    }
    const defaultHeight = parseInt(config.defaultRows, 10);
    if (isFinite(defaultHeight) && defaultHeight > 0) {
      visualizationOptions.sizeY = defaultHeight;
    }
  }

  return visualizationOptions;
}

export const ParameterMappingType = {
  DashboardLevel: "dashboard-level",
  WidgetLevel: "widget-level",
  StaticValue: "static-value",
};

class Widget {
  static MappingType = ParameterMappingType;

  constructor(data) {
    // Copy properties
    extend(this, data);

    // The drawing code is a separate chunk now, and a dashboard knows which
    // types it holds well before any query result comes back. Start fetching
    // here and the chunk has almost always landed by the time there is
    // anything to draw.
    if (this.visualization) {
      preloadVisualization(this.visualization.type);
    }

    const visualizationOptions = calculatePositionOptions(this);

    this.options = this.options || {};
    this.options.position = extend(
      {},
      visualizationOptions,
      pick(this.options.position, ["col", "row", "sizeX", "sizeY", "autoHeight"])
    );

    if (this.options.position.sizeY < 0) {
      this.options.position.autoHeight = true;
    }
  }

  get type() {
    if (this.visualization) {
      return WidgetTypeEnum.VISUALIZATION;
    } else if (this.restricted) {
      return WidgetTypeEnum.RESTRICTED;
    }
    return WidgetTypeEnum.TEXTBOX;
  }

  getQuery() {
    if (!this.query && this.visualization) {
      this.query = new Query(this.visualization.query);
    }

    return this.query;
  }

  getQueryResult() {
    return this.data;
  }

  getName() {
    if (this.visualization) {
      return `${this.visualization.query.name} (${this.visualization.name})`;
    }
    return truncate(this.text, 20);
  }

  /**
   * Load the widget's result.
   *
   * `request` says how fresh it has to be, by intent rather than by number --
   * see services/freshness. Only `onPageLoad` settles for a result already in
   * hand; every other intent fetches, even if this widget is showing
   * something.
   *
   * @param {import("./freshness").Freshness} request
   */
  load(request = onPageLoad()) {
    if (!this.visualization) {
      return Promise.resolve();
    }

    // Both `this.data` and `this.queryResult` are query result objects;
    // `this.data` is last loaded query result;
    // `this.queryResult` is currently loading query result;
    // while widget is refreshing, `this.data` !== `this.queryResult`

    if (!request.reuseLoaded || this.queryResult === undefined) {
      // Widgets showing the same query with the same parameters would each
      // fetch and parse the same result. They share one request instead --
      // see services/inFlightResults.
      this.trackResult(
        shareInFlight(this.resultKey(request), () =>
          request.resultId
            ? QueryResult.getById(this.getQuery().id, request.resultId)
            : this.getQuery().getQueryResult(request)
        )
      );
    }

    return this.queryResult.toPromise();
  }

  /**
   * What this widget is about to ask for, as one value.
   *
   * Two widgets with the same key would send the same request, so one of them
   * can send it for both. It mirrors what `Query.getQueryResult` builds a
   * request from -- the query, its parameter values and whether the auto limit
   * applies -- plus what the caller asked of it.
   *
   * Null means "cannot say", and nothing is shared: a widget with no
   * visualization has nothing to fetch at all.
   */
  resultKey(request) {
    if (!this.visualization) {
      return null;
    }
    const query = this.getQuery();
    return JSON.stringify([
      query.id,
      query.getParameters().getExecutionValues(),
      query.getAutoLimit(),
      request.maxAge === undefined ? null : request.maxAge,
      request.resultId === undefined ? null : request.resultId,
    ]);
  }

  /**
   * Hold a result and follow it to done.
   *
   * Shared by the widget that sent the request and any that joined it, so a
   * widget showing somebody else's result behaves exactly like one showing its
   * own -- same spinner, same error, same moment it stops loading.
   */
  trackResult(queryResult) {
    this.loading = true;
    this.refreshStartedAt = moment();
    this.queryResult = queryResult;

    queryResult
      .toPromise()
      .then((result) => {
        if (this.queryResult === queryResult) {
          this.loading = false;
          this.data = result;
        }
        return result;
      })
      .catch((error) => {
        if (this.queryResult === queryResult) {
          this.loading = false;
          this.data = error;
        }
        return error;
      });
  }

  save(key, value) {
    const data = pick(this, "options", "text", "id", "width", "dashboard_id", "visualization_id");
    if (key && value) {
      data[key] = merge({}, data[key], value); // done like this so `this.options` doesn't get updated by side-effect
    }

    let url = "api/widgets";
    if (this.id) {
      url = `${url}/${this.id}`;
    }

    return axios.post(url, data).then((data) => {
      each(data, (v, k) => {
        this[k] = v;
      });

      return this;
    });
  }

  delete() {
    const url = `api/widgets/${this.id}`;
    return axios.delete(url);
  }

  isStaticParam(param) {
    const mappings = this.getParameterMappings();
    const mappingType = mappings[param.name].type;
    return mappingType === Widget.MappingType.StaticValue;
  }

  getParametersDefs() {
    const mappings = this.getParameterMappings();
    // textboxes does not have query
    const params = this.getQuery() ? this.getQuery().getParametersDefs() : [];

    const queryParams = location.search;

    const localTypes = [Widget.MappingType.WidgetLevel, Widget.MappingType.StaticValue];
    const localParameters = map(
      filter(params, (param) => localTypes.indexOf(mappings[param.name].type) >= 0),
      (param) => {
        const mapping = mappings[param.name];
        const result = cloneParameter(param);
        result.title = mapping.title || param.title;
        result.locals = [param];
        result.urlPrefix = `p_w${this.id}_`;
        if (mapping.type === Widget.MappingType.StaticValue) {
          result.setValue(mapping.value);
        } else {
          result.fromUrlParams(queryParams);
        }
        return result;
      }
    );

    // order widget params using paramOrder
    return sortBy(localParameters, (param) =>
      includes(this.options.paramOrder, param.name)
        ? indexOf(this.options.paramOrder, param.name)
        : size(this.options.paramOrder)
    );
  }

  getParameterMappings() {
    if (!isObject(this.options.parameterMappings)) {
      this.options.parameterMappings = {};
    }

    const existingParams = {};
    // textboxes does not have query
    const params = this.getQuery() ? this.getQuery().getParametersDefs(false) : [];
    each(params, (param) => {
      existingParams[param.name] = true;
      if (!isObject(this.options.parameterMappings[param.name])) {
        // "migration" for old dashboards: parameters with `global` flag
        // should be mapped to a dashboard-level parameter with the same name
        this.options.parameterMappings[param.name] = {
          name: param.name,
          type: param.global ? Widget.MappingType.DashboardLevel : Widget.MappingType.WidgetLevel,
          mapTo: param.name, // map to param with the same name
          value: null, // for StaticValue
          title: "", // Use parameter's title
        };
      }
    });

    // Remove mappings for parameters that do not exists anymore
    const removedParams = difference(keys(this.options.parameterMappings), keys(existingParams));
    each(removedParams, (name) => {
      delete this.options.parameterMappings[name];
    });

    return this.options.parameterMappings;
  }

  getLocalParameters() {
    return filter(this.getParametersDefs(), (param) => !this.isStaticParam(param));
  }
}

export default Widget;
