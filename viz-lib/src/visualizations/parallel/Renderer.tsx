import React, { useMemo } from "react";
import { RendererPropTypes } from "@/visualizations/prop-types";
import echarts from "@/visualizations/echarts";
import useEChart from "@/visualizations/echarts/useEChart";
import { ParallelChart } from "echarts/charts";
import { ParallelComponent } from "echarts/components";
import Problem from "../shared/components/Problem";
import buildOption from "./buildOption";
import "./renderer.less";

// Only this one draws these, so they travel in its own chunk.
echarts.use([ParallelChart, ParallelComponent]);

export default function Renderer({ data, options }: any) {
  const built = useMemo(() => buildOption(data, options), [data, options]);
  const { setContainer } = useEChart(built.problem ? {} : built.option, built.signature);

  if (built.problem) {
    return (
      <div className="parallel-visualization-container">
        <Problem>{built.problem}</Problem>
      </div>
    );
  }

  return <div className="parallel-visualization-container" ref={setContainer} />;
}

Renderer.propTypes = RendererPropTypes;
