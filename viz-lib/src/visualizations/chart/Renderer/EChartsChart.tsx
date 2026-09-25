import React, { useCallback, useEffect, useMemo, useState } from "react";
import { RendererPropTypes } from "@/visualizations/prop-types";
import useEChart from "@/visualizations/echarts/useEChart";
import useElementSize from "@/visualizations/shared/useElementSize";
import trim from "lodash/trim";
import getChartData from "../getChartData";
import buildOption, { buildLinkContext, fillLinkTemplate } from "../echarts/buildOption";

export interface EChartsChartProps {
  data: { rows: any[]; columns: any[] };
  options: any;
}

export default function EChartsChart({ options, data }: EChartsChartProps) {
  const [box, setBox] = useState<HTMLDivElement | null>(null);
  const size = useElementSize(box);
  // Rounded to 10px, the way the gauge does it, so a widget being dragged
  // does not rebuild the chart on every pixel. Height is all that is read --
  // it decides how many y labels fit.
  const bucket = { width: Math.round(size.width / 10) * 10, height: Math.round(size.height / 10) * 10 };
  const built = useMemo(
    () => buildOption(getChartData(data.rows, options), options, bucket.height ? bucket : undefined),
    [data, options, bucket.height] // eslint-disable-line react-hooks/exhaustive-deps
  );
  const { setContainer, chart } = useEChart(built.option, built.signature);

  useEffect(() => {
    if (!chart || !options.enableLink) {
      return;
    }
    const handler = (params: any) => {
      if (!options.linkFormat) {
        return;
      }
      // The template is filled in from the point that was clicked. Opening it
      // as written -- which is what this did -- sends the browser to a URL
      // with "{{ @@x }}" still in it, so the feature the editor documents did
      // nothing at all.
      const href = trim(fillLinkTemplate(options.linkFormat, buildLinkContext(built.option, params, options)));
      if (href) {
        window.open(href, options.linkOpenNewTab ? "_blank" : "_self");
      }
    };
    chart.on("click", handler);
    return () => chart.off("click", handler);
  }, [chart, built.option, options, options.enableLink, options.linkFormat, options.linkOpenNewTab]);

  // The same element is both the measured box and the chart's container;
  // memoised so React does not detach and reattach it on every render.
  const setRefs = useCallback(
    (element: HTMLDivElement | null) => {
      setBox(element);
      setContainer(element);
    },
    [setContainer]
  );

  return <div className="chart-visualization-container" ref={setRefs} />;
}

EChartsChart.propTypes = RendererPropTypes;
