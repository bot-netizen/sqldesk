import React, { useMemo } from "react";
import { RendererPropTypes } from "@/visualizations/prop-types";
import useEChart from "@/visualizations/echarts/useEChart";

import { SankeyDataType } from "./index";
import buildOption from "./buildOption";
import "./renderer.less";

export default function Renderer({ data }: { data: SankeyDataType }) {
  const built = useMemo(() => buildOption(data), [data]);
  const { setContainer } = useEChart(built.option, built.signature);

  return <div className="sankey-visualization-container" ref={setContainer} />;
}

Renderer.propTypes = RendererPropTypes;
