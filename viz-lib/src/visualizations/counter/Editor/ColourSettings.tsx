import React from "react";
import { UpdateOptionsStrategy } from "@/components/visualizations/editor/createTabbedEditor";
import { ThresholdsSection } from "../../shared/valueOptions/editor";

export default function ColourSettings({ options, onOptionsChange }: any) {
  return (
    <ThresholdsSection
      thresholds={options.thresholds}
      testPrefix="Counter"
      description="Colour the number by its value. With no thresholds, it is coloured green or red against the target value, as before."
      onChange={(thresholds) => onOptionsChange({ thresholds }, UpdateOptionsStrategy.shallowMerge)}
    />
  );
}
