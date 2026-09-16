/* eslint-disable react/prop-types */
import React from "react";
import createTabbedEditor from "@/components/visualizations/editor/createTabbedEditor";

import GeneralSettings from "./GeneralSettings";
import XAxisSettings from "./XAxisSettings";
import YAxisSettings from "./YAxisSettings";
import SeriesSettings from "./SeriesSettings";
import ColorsSettings from "./ColorsSettings";
import DataLabelsSettings from "./DataLabelsSettings";

import "./editor.less";

const isPieChart = (options: any) => options.globalSeriesType === "pie";

export default createTabbedEditor([
  {
    key: "General",
    title: "General",
    component: GeneralSettings,
  },
  {
    key: "XAxis",
    title: ({ swappedAxes }: any) => (!swappedAxes ? "X Axis" : "Y Axis"),
    component: XAxisSettings,
    isAvailable: (options: any) => !isPieChart(options),
  },
  {
    key: "YAxis",
    title: ({ swappedAxes }: any) => (!swappedAxes ? "Y Axis" : "X Axis"),
    component: YAxisSettings,
    isAvailable: (options: any) => !isPieChart(options),
  },
  {
    key: "Series",
    title: "Series",
    component: SeriesSettings,
  },
  {
    key: "Colors",
    title: "Colors",
    component: ColorsSettings,
  },
  {
    key: "DataLabels",
    title: "Data Labels",
    component: DataLabelsSettings,
  },
]);
