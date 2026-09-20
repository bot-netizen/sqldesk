import React, { useMemo, useState } from "react";
import { RendererPropTypes } from "@/visualizations/prop-types";
import echarts from "@/visualizations/echarts";
import useEChart from "@/visualizations/echarts/useEChart";
import { CalendarComponent } from "echarts/components";
import useElementSize from "../shared/useElementSize";
import buildOption from "./buildOption";
import "./renderer.less";

// Only the calendar uses this coordinate system, so it travels in the
// calendar's chunk rather than in the one every chart shares.
echarts.use([CalendarComponent]);

export default function Renderer({ data, options }: any) {
  const [box, setBox] = useState<HTMLDivElement | null>(null);
  const size = useElementSize(box);
  // A calendar cannot stretch: seven rows of days, as many columns as there
  // are weeks. It has to know its box to pick a square size. Rounded to 10px
  // so dragging a widget does not rebuild the chart on every pixel.
  const bucket = { width: Math.round(size.width / 10) * 10, height: Math.round(size.height / 10) * 10 };
  const built = useMemo(
    () => buildOption(data, options, bucket.width && bucket.height ? bucket : undefined),
    [data, options, bucket.width, bucket.height] // eslint-disable-line react-hooks/exhaustive-deps
  );
  const { setContainer } = useEChart(built.problem ? {} : built.option, built.signature);

  return (
    <div className="calendar-visualization-container" ref={setBox}>
      {built.problem ? (
        <p className="calendar-visualization-problem">{built.problem}</p>
      ) : (
        <React.Fragment>
          {/* The calendar takes the height it needs to stay legible, and the
              container scrolls to it -- squashed to fit, it says nothing. */}
          <div className="calendar-visualization-chart" style={{ height: built.height }} ref={setContainer} />
          {built.note && <p className="calendar-visualization-note">{built.note}</p>}
        </React.Fragment>
      )}
    </div>
  );
}

Renderer.propTypes = RendererPropTypes;
