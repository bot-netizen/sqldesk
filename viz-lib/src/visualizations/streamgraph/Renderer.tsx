import React, { useMemo } from "react";
import { RendererPropTypes } from "@/visualizations/prop-types";
import echarts from "@/visualizations/echarts";
import useEChart from "@/visualizations/echarts/useEChart";
import { ThemeRiverChart } from "echarts/charts";
import { SingleAxisComponent } from "echarts/components";
import Problem from "../shared/components/Problem";
import buildOption from "./buildOption";
import "./renderer.less";

// Only the streamgraph draws these, so they travel in its chunk rather than
// in the one every ECharts visualization shares.
echarts.use([ThemeRiverChart, SingleAxisComponent]);

export default function Renderer({ data, options }: any) {
  const built = useMemo(() => buildOption(data, options), [data, options]);
  const { setContainer } = useEChart(built.problem ? {} : built.option, built.signature);

  if (built.problem) {
    return (
      <div className="streamgraph-visualization-container">
        <Problem>{built.problem}</Problem>
      </div>
    );
  }

  return <div className="streamgraph-visualization-container" ref={setContainer} />;
}

Renderer.propTypes = RendererPropTypes;
