import React, { useMemo, useState } from "react";
import { RendererPropTypes } from "@/visualizations/prop-types";
import echarts from "@/visualizations/echarts";
import useEChart from "@/visualizations/echarts/useEChart";
import { RadarChart } from "echarts/charts";
import { RadarComponent } from "echarts/components";
import useElementSize from "../shared/useElementSize";
import Problem from "../shared/components/Problem";
import buildOption from "./buildOption";
import "./renderer.less";

// Only the radar draws these, so they travel in its chunk rather than in
// the one every ECharts visualization shares.
echarts.use([RadarChart, RadarComponent]);

export default function Renderer({ data, options }: any) {
  const [box, setBox] = useState<HTMLDivElement | null>(null);
  const size = useElementSize(box);
  // The web is placed in pixels, so it has to know its box. Rounded to 10px so
  // dragging a widget does not rebuild the chart on every pixel.
  const bucket = { width: Math.round(size.width / 10) * 10, height: Math.round(size.height / 10) * 10 };
  const built = useMemo(
    () => buildOption(data, options, bucket.width && bucket.height ? bucket : undefined),
    [data, options, bucket.width, bucket.height] // eslint-disable-line react-hooks/exhaustive-deps
  );
  const { setContainer } = useEChart(built.problem ? {} : built.option, built.signature);

  if (built.problem) {
    return (
      <div className="radar-visualization-container" ref={setBox}>
        <Problem>{built.problem}</Problem>
      </div>
    );
  }

  return (
    <div className="radar-visualization-container" ref={setBox}>
      <div className="radar-visualization-chart" ref={setContainer} />
      {built.note && <p className="radar-visualization-note">{built.note}</p>}
    </div>
  );
}

Renderer.propTypes = RendererPropTypes;
