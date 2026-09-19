import React, { useMemo, useState } from "react";
import { RendererPropTypes } from "@/visualizations/prop-types";
import useEChart from "@/visualizations/echarts/useEChart";
import useElementSize from "../shared/useElementSize";
import buildOption from "./buildOption";
import "./renderer.less";

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
        <p className="gauge-visualization-problem">{built.problem}</p>
      ) : (
        <div className="gauge-visualization-chart" ref={setContainer} />
      )}
    </div>
  );
}

Renderer.propTypes = RendererPropTypes;
