import { castArray, isEqual, map, find, fromPairs, some } from "lodash";
import React, { useState, useMemo, useEffect, useRef } from "react";
import PropTypes from "prop-types";
import useQueryResultData from "@/lib/useQueryResultData";
import useImmutableCallback from "@/lib/hooks/useImmutableCallback";
import Filters, { FiltersType, filterData } from "@/components/Filters";
import { VisualizationType } from "@sqldesk/viz/lib";
import { Renderer } from "@/components/visualizations/visualizationComponents";

function combineFilters(localFilters, globalFilters) {
  // tiny optimization - to avoid unnecessary updates
  if (localFilters.length === 0 || globalFilters.length === 0) {
    return localFilters;
  }

  return map(localFilters, (localFilter) => {
    const globalFilter = find(globalFilters, (f) => f.name === localFilter.name);
    if (globalFilter) {
      return {
        ...localFilter,
        current: globalFilter.current,
      };
    }
    return localFilter;
  });
}

/*
  Fresh filters from a new result, keeping what somebody chose where it still
  exists. Every new result -- a live dashboard's refresh, a streaming query's
  two-second tick -- used to reset each filter to its first value, so a
  selection lasted until the next refresh.
*/
export function keepSelections(fresh, previous) {
  return map(fresh, (current) => {
    const before = find(previous, (f) => f.name === current.name);
    if (!before) {
      return current;
    }
    const exists = (value) => some(current.values, (candidate) => isEqual(candidate, value));
    if (current.multiple) {
      const kept = castArray(before.current || []).filter(exists);
      return kept.length ? { ...current, current: kept } : current;
    }
    return exists(before.current) ? { ...current, current: before.current } : current;
  });
}

function areFiltersEqual(a, b) {
  if (a.length !== b.length) {
    return false;
  }

  a = fromPairs(map(a, (item) => [item.name, item]));
  b = fromPairs(map(b, (item) => [item.name, item]));

  return isEqual(a, b);
}

export default function VisualizationRenderer(props) {
  const data = useQueryResultData(props.queryResult);
  const [filters, setFilters] = useState(() => combineFilters(data.filters, props.filters)); // lazy initialization
  const filtersRef = useRef();
  filtersRef.current = filters;

  const handleFiltersChange = useImmutableCallback((newFilters) => {
    if (!areFiltersEqual(newFilters, filters)) {
      setFilters(newFilters);
      props.onFiltersChange(newFilters);
    }
  });

  // New query results bring new filter values; what somebody had chosen is
  // kept where it is still among them.
  useEffect(() => {
    handleFiltersChange(combineFilters(keepSelections(data.filters, filtersRef.current), props.filters));
  }, [data.filters, props.filters, handleFiltersChange]);

  // Update local filters when global filters changed.
  // For correct behavior need to watch only `props.filters` here,
  // therefore using ref to access current local filters
  useEffect(() => {
    handleFiltersChange(combineFilters(filtersRef.current, props.filters));
  }, [props.filters, handleFiltersChange]);

  const filteredData = useMemo(
    () => ({
      columns: data.columns,
      rows: filterData(data.rows, filters),
    }),
    [data, filters]
  );

  const { showFilters, visualization } = props;

  let options = { ...visualization.options };

  // define pagination size based on context for Table visualization
  if (visualization.type === "TABLE") {
    options.paginationSize = props.context === "widget" ? "small" : "default";
  }

  return (
    <Renderer
      key={`visualization${visualization.id}`}
      type={visualization.type}
      options={options}
      data={filteredData}
      visualizationName={visualization.name}
      addonBefore={showFilters && <Filters filters={filters} onChange={handleFiltersChange} />}
    />
  );
}

VisualizationRenderer.propTypes = {
  visualization: VisualizationType.isRequired,
  queryResult: PropTypes.object.isRequired, // eslint-disable-line react/forbid-prop-types
  showFilters: PropTypes.bool,
  filters: FiltersType,
  onFiltersChange: PropTypes.func,
  context: PropTypes.oneOf(["query", "widget"]).isRequired,
};

VisualizationRenderer.defaultProps = {
  showFilters: true,
  filters: [],
  onFiltersChange: () => {},
};
