import React, { useMemo } from "react";
import echarts from "@/visualizations/echarts";
import useEChart from "@/visualizations/echarts/useEChart";
import { FunnelChart } from "echarts/charts";
import { AllColorPaletteArrays, resolveColorScheme, DEFAULT_COLOR_SCHEME } from "@/visualizations/ColorPalette";
import { uiColor } from "@/visualizations/shared/valueOptions";
import { ECHARTS_MOTION } from "@/visualizations/shared/motion";

import "./drawn-funnel.less";

// Only the drawn funnel uses this, so it travels in the funnel's chunk.
echarts.use([FunnelChart]);

interface Step {
  step: string;
  value: number;
  pctMax: number;
  pctPrevious: number;
}

/**
 * The funnel drawn as a funnel.
 *
 * Width carries the value, so the taper between two bands *is* the drop-off --
 * which is the thing the table look states in a column and this one shows.
 * The table stays the default, and stays an option, because it is better at
 * exact numbers and at more than a handful of steps.
 */
export default function DrawnFunnel({
  steps,
  formatValue,
  formatPercentValue,
  stepLabel,
}: {
  steps: Step[];
  formatValue: (v: any) => string;
  formatPercentValue: (v: any) => string;
  stepLabel: string;
}) {
  const option = useMemo(() => {
    const palette = (AllColorPaletteArrays as any)[resolveColorScheme(DEFAULT_COLOR_SCHEME)];
    const muted = uiColor("muted");

    return {
      ...ECHARTS_MOTION,
      aria: {
        enabled: true,
        label: {
          description: `A funnel of ${steps.length} steps from ${steps[0].step} to ${
            steps[steps.length - 1].step
          }, narrowing from ${formatValue(steps[0].value)} to ${formatValue(steps[steps.length - 1].value)}.`,
        },
      },
      color: palette,
      tooltip: {
        trigger: "item",
        confine: true,
        formatter: (params: any) => {
          const step = steps[params.dataIndex];
          return [
            `${stepLabel}: ${step.step}`,
            `<b>${formatValue(step.value)}</b>`,
            `${formatPercentValue(step.pctMax)} of the first step`,
            params.dataIndex > 0 ? `${formatPercentValue(step.pctPrevious)} of the one before` : null,
          ]
            .filter(Boolean)
            .join("<br/>");
        },
      },
      series: [
        {
          id: "funnel",
          type: "funnel",
          left: 8,
          right: 8,
          top: 12,
          bottom: 12,
          minSize: "12%",
          maxSize: "100%",
          // The rows arrive already sorted by prepareData, which honours the
          // visualization's own sort settings; sorting again here would
          // silently override them.
          sort: "none",
          gap: 2,
          // Each band's width is its share of the largest step, so the shape
          // is the drop-off rather than a decoration around it.
          data: steps.map((step, i) => ({
            name: step.step,
            value: step.pctMax,
            itemStyle: { color: palette[i % palette.length], borderColor: "#fff", borderWidth: 1 },
          })),
          label: {
            show: true,
            position: "inside",
            formatter: (params: any) => `${params.name}  ${formatValue(steps[params.dataIndex].value)}`,
            color: "#fff",
            fontSize: 12,
            overflow: "truncate",
          },
          labelLine: { show: false },
          emphasis: { label: { fontSize: 13 } },
        },
      ],
      // Steps beyond the first are named down the side when the band is too
      // narrow to hold a name.
      textStyle: { color: muted },
    };
  }, [steps, formatValue, formatPercentValue, stepLabel]);

  // The steps are the shape; new values for the same steps can tween.
  const signature = useMemo(() => JSON.stringify(steps.map((s) => s.step)), [steps]);
  const { setContainer } = useEChart(option, signature);

  return <div className="funnel-visualization-chart" ref={setContainer} />;
}
