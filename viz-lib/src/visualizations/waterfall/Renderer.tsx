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
      <div className="waterfall-visualization-container">
        <p className="waterfall-visualization-problem">{built.problem}</p>
      </div>
    );
  }

  return (
    <div className="waterfall-visualization-container">
      <div className="waterfall-visualization-chart" ref={setContainer} />
      {built.note && <p className="waterfall-visualization-note">{built.note}</p>}
    </div>
  );
}

Renderer.propTypes = RendererPropTypes;
