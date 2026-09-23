import React, { useMemo } from "react";
import { RendererPropTypes } from "@/visualizations/prop-types";
import echarts from "@/visualizations/echarts";
import useEChart from "@/visualizations/echarts/useEChart";
import { TreemapChart } from "echarts/charts";
import Problem from "../shared/components/Problem";
import buildOption from "./buildOption";
import "./renderer.less";

// Only the treemap draws this, so it travels in the treemap's chunk.
echarts.use([TreemapChart]);

export default function Renderer({ data, options }: any) {
  const built = useMemo(() => buildOption(data, options), [data, options]);
  const { setContainer } = useEChart(built.problem ? {} : built.option, built.signature);

  if (built.problem) {
    return (
      <div className="treemap-visualization-container">
        <Problem>{built.problem}</Problem>
      </div>
    );
  }

  return (
    <div className="treemap-visualization-container">
      <div className="treemap-visualization-chart" ref={setContainer} />
      {built.note && <p className="treemap-visualization-note">{built.note}</p>}
    </div>
  );
}

Renderer.propTypes = RendererPropTypes;
