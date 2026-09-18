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
      <div className="progress-visualization-container">
        <p className="progress-visualization-problem">{built.problem}</p>
      </div>
    );
  }

  // Height follows the number of bars, so a four-row result is not stretched
  // across a tall widget and a forty-row one is not crushed into a short one.
  const height = Math.max(140, built.rows.length * 34 + 40);
  return (
    <div className="progress-visualization-container">
      <div className="progress-visualization-chart" style={{ height }} ref={setContainer} />
      {built.note && <p className="progress-visualization-note">{built.note}</p>}
    </div>
  );
}

Renderer.propTypes = RendererPropTypes;
