import React, { useMemo } from "react";
import { RendererPropTypes } from "@/visualizations/prop-types";
import useEChart from "@/visualizations/echarts/useEChart";

import Problem from "../shared/components/Problem";
import buildOption from "./buildOption";
import "./renderer.less";

export default function Renderer({ data }: any) {
  const built = useMemo(() => buildOption(data), [data]);
  const { setContainer } = useEChart(built.problem ? {} : built.option, built.signature);

  if (built.problem) {
    return <Problem>{built.problem}</Problem>;
  }

  return <div className="sunburst-visualization-container" ref={setContainer} />;
}

Renderer.propTypes = RendererPropTypes;
