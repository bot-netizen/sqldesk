import React, { useMemo, useState } from "react";
import { RendererPropTypes } from "@/visualizations/prop-types";
import echarts from "@/visualizations/echarts";
import useEChart from "@/visualizations/echarts/useEChart";
import { GraphicComponent } from "echarts/components";
import useElementSize from "../shared/useElementSize";
import Problem from "../shared/components/Problem";
import buildOption from "./buildOption";
import "./renderer.less";

// The reading tile writes the ends of its range under the bullet bar with
// `graphic`, which only this visualization uses -- so it travels in the
// gauge's chunk rather than in the one every ECharts visualization shares.
//
// Without this the labels are not drawn and nothing says so: an unregistered
// component makes ECharts ignore its part of the option in silence.
echarts.use([GraphicComponent]);

export default function Renderer({ data, options }: any) {
  const [box, setBox] = useState<HTMLDivElement | null>(null);
  const size = useElementSize(box);
  // Size is rounded to 10px so a widget being dragged does not rebuild the
  // chart on every pixel.
  const bucket = { width: Math.round(size.width / 10) * 10, height: Math.round(size.height / 10) * 10 };
  const built = useMemo(
    () => buildOption(data, options, bucket.width && bucket.height ? bucket : undefined),
    [data, options, bucket.width, bucket.height] // eslint-disable-line react-hooks/exhaustive-deps
  );
  const { setContainer } = useEChart(built.problem ? {} : built.option, built.signature);

  return (
    <div className="gauge-visualization-container" ref={setBox}>
      {built.problem ? (
        <Problem>{built.problem}</Problem>
      ) : (
        <div className="gauge-visualization-chart" ref={setContainer} />
      )}
    </div>
  );
}

Renderer.propTypes = RendererPropTypes;
