import React, { useMemo } from "react";
import { RendererPropTypes } from "@/visualizations/prop-types";
import useEChart from "@/visualizations/echarts/useEChart";

import Problem from "../shared/components/Problem";
import buildOption from "./buildOption";
import "./renderer.less";

export default function Renderer({ data, options }: any) {
  const built = useMemo(() => buildOption(data, options), [data, options]);
  const { setContainer } = useEChart(built.problem ? {} : built.option, built.signature);

  if (built.problem) {
    return (
      <div className="box-plot-deprecated-visualization-container">
        <Problem>{built.problem}</Problem>
      </div>
    );
  }

  return <div className="box-plot-deprecated-visualization-container" ref={setContainer} />;
}

Renderer.propTypes = RendererPropTypes;
