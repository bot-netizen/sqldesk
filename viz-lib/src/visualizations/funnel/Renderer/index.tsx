import { maxBy } from "lodash";
import React, { useMemo } from "react";
import Table from "antd/lib/table";
import Tooltip from "antd/lib/tooltip";
import { RendererPropTypes } from "@/visualizations/prop-types";
import { AllColorPaletteArrays, resolveColorScheme, DEFAULT_COLOR_SCHEME } from "@/visualizations/ColorPalette";
import { createNumberFormatter } from "@/lib/value-format";
import Problem, { NO_ROWS } from "@/visualizations/shared/components/Problem";

import prepareData from "./prepareData";
import FunnelBar from "./FunnelBar";
import DrawnFunnel from "./DrawnFunnel";
import "./index.less";

export default function Renderer({ data, options }: any) {
  const funnelData = useMemo(() => prepareData(data.rows, options), [data, options]);

  const formatValue = useMemo(() => createNumberFormatter(options.numberFormat), [options.numberFormat]);

  const formatPercentValue = useMemo(() => {
    const format = createNumberFormatter(options.percentFormat);
    return (value: any) => {
      if (value < options.percentValuesRange.min) {
        return `<${format(options.percentValuesRange.min)}`;
      }
      if (value > options.percentValuesRange.max) {
        return `>${format(options.percentValuesRange.max)}`;
      }
      return format(value);
    };
  }, [options.percentFormat, options.percentValuesRange]);

  // The same colour the drawn shape starts on, and the theme's, rather than
  // the one hex the table look was written with in 2017 -- a cyan that belongs
  // to no palette we ship and does not follow the dark wall display.
  const barColor = useMemo(() => {
    const palette = (AllColorPaletteArrays as any)[resolveColorScheme(DEFAULT_COLOR_SCHEME)];
    return palette[0];
  }, []);

  const columns = useMemo(() => {
    if (funnelData.length === 0) {
      return [];
    }

    // @ts-expect-error ts-migrate(2532) FIXME: Object is possibly 'undefined'.
    const maxToPrevious = maxBy(funnelData, (d) => (isFinite(d.pctPrevious) ? d.pctPrevious : 0)).pctPrevious;
    return [
      {
        title: options.stepCol.displayAs,
        dataIndex: "step",
        width: "25%",
        className: "text-ellipsis",
        render: (text: any) => (
          <Tooltip title={text} mouseEnterDelay={0} mouseLeaveDelay={0}>
            {text}
          </Tooltip>
        ),
      },
      {
        title: options.valueCol.displayAs,
        dataIndex: "value",
        width: "45%",
        align: "center",
        render: (value: any, item: any) => (
          // @ts-expect-error ts-migrate(2745) FIXME: This JSX tag's 'children' prop expects type 'never... Remove this comment to see the full error message
          <FunnelBar align="center" color={barColor} value={item.pctMax}>
            {formatValue(value)}
          </FunnelBar>
        ),
      },
      {
        title: "% Max",
        dataIndex: "pctMax",
        width: "15%",
        align: "center",
        render: (value: any) => formatPercentValue(value),
      },
      {
        title: "% Previous",
        dataIndex: "pctPrevious",
        width: "15%",
        align: "center",
        render: (value: any) => (
          // @ts-expect-error ts-migrate(2745) FIXME: This JSX tag's 'children' prop expects type 'never... Remove this comment to see the full error message
          <FunnelBar className="funnel-percent-column" value={(value / maxToPrevious) * 100.0}>
            {formatPercentValue(value)}
          </FunnelBar>
        ),
      },
    ];
  }, [options.stepCol.displayAs, options.valueCol.displayAs, funnelData, formatValue, formatPercentValue, barColor]);

  if (funnelData.length === 0) {
    // It used to render nothing at all -- an empty widget, with no way to tell
    // a query that returned nothing from a funnel that was never finished
    // being set up.
    return (
      <Problem>
        {!options.stepCol.colName || !options.valueCol.colName
          ? "Choose a step column and a value column in the editor."
          : NO_ROWS}
      </Problem>
    );
  }

  if (options.shape === "funnel") {
    return (
      <div className="funnel-visualization-container">
        {/* createNumberFormatter only returns an element when asked to, and
            the funnel does not ask: these are strings. */}
        <DrawnFunnel
          steps={funnelData as any}
          formatValue={formatValue as (v: any) => string}
          formatPercentValue={formatPercentValue as (v: any) => string}
          stepLabel={options.stepCol.displayAs}
        />
      </div>
    );
  }

  return (
    <div className="funnel-visualization-container">
      <Table
        // @ts-expect-error ts-migrate(2322) FIXME: Type '({ title: any; dataIndex: string; width: str... Remove this comment to see the full error message
        columns={columns}
        dataSource={funnelData}
        // A step's identity is its position in the funnel. The key used to
        // carry a random prefix regenerated on every data change, so every row
        // was torn down and rebuilt on every refresh -- on a live dashboard,
        // every few seconds, for a table whose contents React can just update.
        rowKey={(record, index) => String(index)}
        pagination={false}
      />
    </div>
  );
}

Renderer.propTypes = RendererPropTypes;
