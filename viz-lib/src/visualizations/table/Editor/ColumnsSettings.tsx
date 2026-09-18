import React from "react";
import SharedColumnsSettings from "../../shared/components/ColumnsSettings";
import CellFormatSection from "./CellFormatSection";
import { EditorPropTypes } from "@/visualizations/prop-types";

export default function ColumnsSettings({ options, onOptionsChange, data }: any) {
  return (
    <SharedColumnsSettings
      options={options}
      onOptionsChange={onOptionsChange}
      variant="table"
      ColumnExtra={CellFormatSection}
    />
  );
}

ColumnsSettings.propTypes = EditorPropTypes;
