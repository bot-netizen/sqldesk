import React, { useMemo } from "react";
import { RendererPropTypes } from "@/visualizations/prop-types";
import echarts from "@/visualizations/echarts";
import useEChart from "@/visualizations/echarts/useEChart";
import { RadarChart } from "echarts/charts";
import { RadarComponent } from "echarts/components";
import buildOption from "./buildOption";
import "./renderer.less";

// Only the radar draws these, so they travel in its chunk rather than in
// the one every ECharts visualization shares.
echarts.use([RadarChart, RadarComponent]);

export default function Renderer({ data, options }: any) {
  const built = useMemo(() => buildOption(data, options), [data, options]);
  const { setContainer } = useEChart(built.problem ? {} : built.option, built.signature);

  if (built.problem) {
    return (
      <div className="radar-visualization-container">
        <p className="radar-visualization-problem">{built.problem}</p>
      </div>
    );
  }

  return (
    <div className="radar-visualization-container">
      <div className="radar-visualization-chart" ref={setContainer} />
      {built.note && <p className="radar-visualization-note">{built.note}</p>}
    </div>
  );
}

Renderer.propTypes = RendererPropTypes;
