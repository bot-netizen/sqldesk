import React, { useMemo } from "react";
import { RendererPropTypes } from "@/visualizations/prop-types";
import useEChart from "@/visualizations/echarts/useEChart";
import buildOption from "./buildOption";
import "./renderer.less";

export default function Renderer({ data, options }: any) {
  const built = useMemo(() => buildOption(data, options), [data, options]);
  const { setContainer } = useEChart(built.problem ? {} : built.option, built.signature);

  if (built.problem) {
    return (
      <div className="histogram-visualization-container">
        <p className="histogram-visualization-problem">{built.problem}</p>
      </div>
    );
  }

  return (
    <div className="histogram-visualization-container">
      <div className="histogram-visualization-chart" ref={setContainer} />
      {built.note && <p className="histogram-visualization-note">{built.note}</p>}
    </div>
  );
}

Renderer.propTypes = RendererPropTypes;
