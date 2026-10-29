import { map, range } from "lodash";
import React from "react";
import AntSelect from "antd/lib/select";
import { UpdateOptionsStrategy } from "@/components/visualizations/editor/createTabbedEditor";
import { ControlLabel, Section } from "@/components/visualizations/editor";
import { MAX_PANELS, panelCount } from "../panels";

/**
 * Whether this chart can be divided into panels.
 *
 * The same rule the renderer applies, so the control is absent rather than
 * present and ignored: a pie has no grid, a heatmap builds its own, a box
 * plot is a distribution per category, and a sideways bar chart runs its
 * categories down the axis the panels would cut.
 */
export function supportsPanels(options: any): boolean {
  return !options.swappedAxes && !["pie", "heatmap", "box"].includes(options.globalSeriesType);
}

/**
 * One control, deliberately.
 *
 * Per-panel titles and heights were built and then cut: they doubled the
 * editor surface of a chart form most people never reach for, and the titles
 * clipped off the left edge whenever a panel's numbers were narrow. Panels
 * are equal, and the axis title on the Y-Axis tab below labels the first.
 */
export default function PanelSettings({ options, onOptionsChange }: any) {
  return (
    <Section>
      <ControlLabel label="Panels">
        <p className="value-options-help">
          Stacked plots sharing this chart's x axis, with one legend and one cursor across them -- for series on scales
          too different to share an axis. Each series picks its panel on the Series tab.
        </p>
        <AntSelect
          value={panelCount(options)}
          onChange={(panels: any) => onOptionsChange({ panels }, UpdateOptionsStrategy.shallowMerge)}
          data-test="Chart.Panels.Count"
          aria-label="Number of panels"
          style={{ width: "100%" }}
        >
          {map(range(1, MAX_PANELS + 1), (n) => (
            <AntSelect.Option key={n} value={n} data-test={`Chart.Panels.Count.${n}`}>
              {n === 1 ? "One plot" : `${n} panels`}
            </AntSelect.Option>
          ))}
        </AntSelect>
      </ControlLabel>
    </Section>
  );
}
