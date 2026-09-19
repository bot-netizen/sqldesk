import { isFinite } from "lodash";
import React, { useState, useEffect, useMemo, useRef } from "react";
import cx from "classnames";
import resizeObserver from "@/services/resizeObserver";
import { RendererPropTypes } from "@/visualizations/prop-types";
import useEChart from "@/visualizations/echarts/useEChart";
import { resolveColor } from "../shared/valueOptions";

import { getCounterData } from "./utils";
import { orderRows, getStatExtras } from "./stat";
import useCountUp from "./useCountUp";

import "./render.less";

function getCounterStyles(scale: any) {
  return {
    msTransform: `scale(${scale})`,
    MozTransform: `scale(${scale})`,
    WebkitTransform: `scale(${scale})`,
    transform: `scale(${scale})`,
  };
}

function getCounterScale(container: any) {
  const inner = container.firstChild;
  const scale = Math.min(container.offsetWidth / inner.offsetWidth, container.offsetHeight / inner.offsetHeight);
  return Number(isFinite(scale) ? scale : 1).toFixed(2); // keep only two decimal places
}

function Sparkline({ points, color }: { points: number[]; color: string }) {
  const option = useMemo(
    () => ({
      grid: { left: 2, right: 8, top: 6, bottom: 2 },
      xAxis: { type: "category", show: false, boundaryGap: false, data: points.map((_, i) => i) },
      yAxis: { type: "value", show: false, scale: true },
      tooltip: { show: false },
      series: [
        {
          type: "line",
          data: points,
          smooth: 0.3,
          symbol: "none",
          lineStyle: { width: 2, color },
          areaStyle: { color, opacity: 0.14 },
          // The latest point is the headline, so it is marked.
          markPoint: {
            symbol: "circle",
            symbolSize: 7,
            label: { show: false },
            itemStyle: { color, borderColor: "#fff", borderWidth: 2 },
            data: [{ coord: [points.length - 1, points[points.length - 1]] }],
          },
          animationDurationUpdate: 700,
        },
      ],
      aria: { enabled: false },
    }),
    [points, color]
  );
  // Same length, same series: the line moves. A different length redraws.
  const { setContainer } = useEChart(option, `spark:${points.length}`);
  return <div className="counter-visualization-sparkline" ref={setContainer} aria-hidden="true" />;
}

export default function Renderer({ data, options, visualizationName }: any) {
  const [scale, setScale] = useState("1.00");
  const [container, setContainer] = useState<any>(null);

  useEffect(() => {
    if (container) {
      const unwatch = resizeObserver(container, () => {
        setScale(getCounterScale(container));
      });
      return unwatch;
    }
  }, [container]);

  useEffect(() => {
    if (container) {
      setScale(getCounterScale(container));
    }
  }, [data, options, container]);

  // With a sparkline the rows are read oldest first and the latest one is the
  // headline, whatever order the query returned them in.
  const rows = useMemo(() => orderRows(data.rows, options, data.columns), [data, options]);
  const sparkOn = options.sparkline && options.sparkline.enabled;
  const counterOptions = sparkOn ? { ...options, rowNumber: -1 } : options;

  const {
    showTrend,
    trendPositive,
    counterValue,
    counterValueRaw,
    counterValueTooltip,
    targetValue,
    targetValueTooltip,
    counterLabel,
  } = getCounterData(rows, counterOptions, visualizationName) as any;

  // The headline from the previous refresh, for "since last refresh". Moved
  // along only when the data object changes, so re-renders for other reasons
  // do not erase it.
  const seen = useRef<{ data: any; value: number | null } | null>(null);
  const previousRefresh = useRef<number | null>(null);
  if (seen.current && seen.current.data !== data) {
    previousRefresh.current = seen.current.value;
  }
  const currentRaw = isFinite(counterValueRaw) ? counterValueRaw : null;
  seen.current = { data, value: currentRaw };

  const extras = useMemo(
    () => getStatExtras(rows, counterOptions, previousRefresh.current),
    // counterOptions is derived from options and sparkOn.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [rows, options, currentRaw]
  );

  // Counts from the previous number to this one. Returns null when there is
  // nothing to animate, so the displayed string is unchanged from before.
  const countingValue = useCountUp(counterValueRaw, options);

  // Thresholds, when set, decide the colour; otherwise the classic trend
  // against the target does, as it always has.
  const useTrend = !extras.valueColor && showTrend;
  const sparkColor = extras.valueColor || resolveColor("accent");

  return (
    <div
      className={cx("counter-visualization-container", {
        "trend-positive": useTrend && trendPositive,
        "trend-negative": useTrend && !trendPositive,
        "counter-visualization-with-sparkline": !!extras.spark,
      })}
    >
      <div className="counter-visualization-content" ref={setContainer}>
        <div style={getCounterStyles(scale)}>
          <div
            className="counter-visualization-value"
            title={counterValueTooltip}
            style={extras.valueColor ? { color: extras.valueColor } : undefined}
          >
            {countingValue ?? counterValue}
          </div>
          {targetValue && (
            <div className="counter-visualization-target" title={targetValueTooltip}>
              ({targetValue})
            </div>
          )}
          {extras.delta && (
            <div className="counter-visualization-delta" data-test="Counter.Delta">
              <span className={`counter-visualization-delta-badge tone-${extras.delta.tone}`}>{extras.delta.text}</span>{" "}
              <span className="counter-visualization-delta-label">{extras.delta.label}</span>
            </div>
          )}
          <div className="counter-visualization-label">{counterLabel}</div>
        </div>
      </div>
      {extras.spark && extras.spark.length > 1 && <Sparkline points={extras.spark} color={sparkColor} />}
    </div>
  );
}

Renderer.propTypes = RendererPropTypes;
