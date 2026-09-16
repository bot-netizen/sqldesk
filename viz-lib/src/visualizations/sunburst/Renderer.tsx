import React, { useMemo } from "react";
import { RendererPropTypes } from "@/visualizations/prop-types";
import useEChart from "@/visualizations/echarts/useEChart";

import buildOption from "./buildOption";
import "./renderer.less";

export default function Renderer({ data }: any) {
  const built = useMemo(() => buildOption(data), [data]);
  const { setContainer } = useEChart(built.option, built.signature);

  return <div className="sunburst-visualization-container" ref={setContainer} />;
}

Renderer.propTypes = RendererPropTypes;
