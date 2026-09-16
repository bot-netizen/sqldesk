import React from "react";
import { RendererPropTypes } from "@/visualizations/prop-types";

import EChartsChart from "./EChartsChart";

import "./renderer.less";

export default function Renderer(props: any) {
  return <EChartsChart {...props} />;
}

Renderer.propTypes = RendererPropTypes;
