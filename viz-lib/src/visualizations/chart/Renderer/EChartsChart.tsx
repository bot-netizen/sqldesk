import React, { useEffect, useMemo } from "react";
import { RendererPropTypes } from "@/visualizations/prop-types";
import useEChart from "@/visualizations/echarts/useEChart";
import getChartData from "../getChartData";
import buildOption from "../echarts/buildOption";

export interface EChartsChartProps {
  data: { rows: any[]; columns: any[] };
  options: any;
}

export default function EChartsChart({ options, data }: EChartsChartProps) {
  const built = useMemo(() => buildOption(getChartData(data.rows, options), options), [data, options]);
  const { setContainer, chart } = useEChart(built.option, built.signature);

  useEffect(() => {
    if (!chart || !options.enableLink) {
      return;
    }
    const handler = () => {
      if (options.linkFormat) {
        window.open(options.linkFormat, options.linkOpenNewTab ? "_blank" : "_self");
      }
    };
    chart.on("click", handler);
    return () => chart.off("click", handler);
  }, [chart, options.enableLink, options.linkFormat, options.linkOpenNewTab]);

  return <div className="chart-visualization-container" ref={setContainer} />;
}

EChartsChart.propTypes = RendererPropTypes;
