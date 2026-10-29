import React, { useCallback } from "react";
import PropTypes from "prop-types";
import { AllColorPalettes } from "@/visualizations/ColorPalette";
import { Section, Switch, InputNumber, ColorPicker } from "@/components/visualizations/editor";

/*
  One breakpoint that colours a bar by its own value.

  A series colour says which measure a bar is; it cannot say whether the number
  is good. On a horizontal bar chart of variances -- the case this was asked
  for -- the sign is the entire message, and a single colour hides it.

  Deliberately one breakpoint rather than a list of bands. Two colours either
  side of a number covers over/under, surplus/shortfall and pass/fail, which is
  nearly every use; a general banding editor is a bigger thing and can be built
  on this option if it is ever wanted.
*/

/** Whether any part of this chart is drawn as bars. */
export function hasBars(options: any) {
  if (options.globalSeriesType === "column") {
    return true;
  }
  return Object.keys(options.seriesOptions || {}).some((name) => options.seriesOptions[name].type === "column");
}

export default function ThresholdColorSettings({ options, onOptionsChange }: any) {
  const threshold = options.valueThreshold || {};

  const update = useCallback(
    (changes: any) => onOptionsChange({ valueThreshold: { ...threshold, ...changes } }),
    [onOptionsChange, threshold]
  );

  // The same presets the series pickers offer, so a threshold colour belongs to
  // the chart's palette rather than being picked out of the air.
  // @ts-expect-error ts-migrate(7053) FIXME: a palette name indexes this; the keys are not a union here.
  const presets = { ...AllColorPalettes[options.color_scheme] };

  return (
    <React.Fragment>
      <Section>
        {/* @ts-expect-error ts-migrate(2745) FIXME: This JSX tag's 'children' prop expects type 'never... Remove this comment to see the full error message */}
        <Switch
          data-test="Chart.ValueThreshold.Enabled"
          // @ts-expect-error ts-migrate(2322) FIXME: Type 'string' is not assignable to type 'never'.
          id="chart-value-threshold"
          // @ts-expect-error ts-migrate(2322) FIXME: Type 'any' is not assignable to type 'never'.
          defaultChecked={threshold.enabled}
          // @ts-expect-error ts-migrate(2322) FIXME: Type '(enabled: boolean) => any' is not assignable to type 'never'.
          onChange={(enabled: boolean) => update({ enabled })}
        >
          Color bars by value
        </Switch>
      </Section>

      {threshold.enabled && (
        <React.Fragment>
          <Section>
            <InputNumber
              label="Breakpoint"
              data-test="Chart.ValueThreshold.Value"
              // A bar exactly at the breakpoint counts as above it, so the
              // default of 0 colours negatives and leaves a zero bar alone.
              defaultValue={threshold.value}
              onChange={(value: any) => update({ value })}
            />
          </Section>
          <Section>
            <ColorPicker
              label="Below the breakpoint"
              data-test="Chart.ValueThreshold.Below"
              interactive
              presetColors={presets}
              placement="topRight"
              color={threshold.below}
              onChange={(below: any) => update({ below })}
              addonAfter={
                // @ts-expect-error ts-migrate(2322) FIXME: Type 'any' is not assignable to type 'never'.
                <ColorPicker.Label color={threshold.below} presetColors={presets} />
              }
            />
          </Section>
          <Section>
            <ColorPicker
              label="At or above it"
              data-test="Chart.ValueThreshold.Above"
              interactive
              presetColors={presets}
              placement="topRight"
              color={threshold.above}
              onChange={(above: any) => update({ above })}
              addonAfter={
                // @ts-expect-error ts-migrate(2322) FIXME: Type 'any' is not assignable to type 'never'.
                <ColorPicker.Label color={threshold.above} presetColors={presets} />
              }
            />
          </Section>
        </React.Fragment>
      )}
    </React.Fragment>
  );
}

// Not EditorPropTypes: this section reads the options and nothing else, so
// requiring `data` would make every caller pass something it never looks at.
ThresholdColorSettings.propTypes = {
  options: PropTypes.object.isRequired,
  onOptionsChange: PropTypes.func.isRequired,
};
