import React, { useState, useEffect, useMemo } from "react";
import { get, find, pick, map, mapValues } from "lodash";
import PivotTableUI from "react-pivottable/PivotTableUI";
import TableRenderers from "react-pivottable/TableRenderers";
import { RendererPropTypes } from "@/visualizations/prop-types";
import { formatColumnValue } from "@/lib/utils";

import "react-pivottable/pivottable.css";
import "./renderer.less";

// react-pivottable's chart renderers are Plotly-based and ship with that
// library rather than with us, so the pivot keeps its table renderers only.
// A pivot saved while the chart renderers existed names one of them in
// `rendererName`; react-pivottable would look it up, find nothing, and render
// `undefined` as a component. Fall back to the first table renderer instead.
const DEFAULT_RENDERER_NAME = Object.keys(TableRenderers)[0];

function resolveRendererName(name: any) {
  return Object.prototype.hasOwnProperty.call(TableRenderers, name) ? name : DEFAULT_RENDERER_NAME;
}

const VALID_OPTIONS = [
  "rows",
  "cols",
  "vals",
  "aggregatorName",
  "valueFilter",
  "sorters",
  "rowOrder",
  "colOrder",
  "derivedAttributes",
  "rendererName",
  "hiddenAttributes",
  "hiddenFromAggregators",
  "hiddenFromDragDrop",
  "menuLimit",
  "unusedOrientationCutoff",
  "controls",
  "rendererOptions",
];

function formatRows({ rows, columns }: any) {
  return map(rows, (row) =>
    mapValues(row, (value, key) => formatColumnValue(value, find(columns, { name: key }).type))
  );
}

export default function Renderer({ data, options, onOptionsChange }: any) {
  const [config, setConfig] = useState({ ...options });
  const dataRows = useMemo(() => formatRows(data), [data]);

  useEffect(() => {
    setConfig({ ...options });
  }, [options]);

  const onChange = (updatedOptions: any) => {
    const validOptions = pick(updatedOptions, VALID_OPTIONS);
    setConfig({ ...validOptions });
    onOptionsChange(validOptions);
  };

  // Legacy behavior: hideControls when controls.enabled is true
  const hideControls = get(options, "controls.enabled");
  const hideRowTotals = !get(options, "rendererOptions.table.rowTotals");
  const hideColumnTotals = !get(options, "rendererOptions.table.colTotals");
  return (
    <div
      className="pivot-table-visualization-container"
      data-hide-controls={hideControls || null}
      data-hide-row-totals={hideRowTotals || null}
      data-hide-column-totals={hideColumnTotals || null}
      data-test="PivotTableVisualization"
    >
      {/* @ts-ignore PivotTableUI types may mismatch with @types/react */}
      <PivotTableUI
        {...pick(config, VALID_OPTIONS)}
        rendererName={resolveRendererName(get(config, "rendererName"))}
        data={dataRows}
        onChange={onChange}
        renderers={TableRenderers}
      />
    </div>
  );
}

Renderer.propTypes = RendererPropTypes;
Renderer.defaultProps = { onOptionsChange: () => {} };
