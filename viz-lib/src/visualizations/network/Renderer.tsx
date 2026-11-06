import React, { useMemo } from "react";
import { RendererPropTypes } from "@/visualizations/prop-types";
import echarts from "@/visualizations/echarts";
import useEChart from "@/visualizations/echarts/useEChart";
import { GraphChart } from "echarts/charts";
import Problem from "../shared/components/Problem";
import buildOption from "./buildOption";
import "./renderer.less";

// Only the network draws this, so it travels in its own chunk.
echarts.use([GraphChart]);

export default function Renderer({ data, options }: any) {
  const built = useMemo(() => buildOption(data, options), [data, options]);
  const { setContainer } = useEChart(built.problem ? {} : built.option, built.signature);

  if (built.problem) {
    return (
      <div className="network-visualization-container">
        <Problem>{built.problem}</Problem>
      </div>
    );
  }

  return <div className="network-visualization-container" ref={setContainer} />;
}

Renderer.propTypes = RendererPropTypes;
