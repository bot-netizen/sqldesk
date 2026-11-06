import { map } from "lodash";
import React from "react";
import { Section, Select, ColorPicker, Switch } from "@/components/visualizations/editor";
import { EditorPropTypes } from "@/visualizations/prop-types";
import ColorPalette from "@/visualizations/ColorPalette";

const ColorSchemes = [
  "Blackbody",
  "Bluered",
  "Blues",
  "Earth",
  "Electric",
  "Greens",
  "Greys",
  "Hot",
  "Jet",
  "Picnic",
  "Portland",
  "Rainbow",
  "RdBu",
  "Reds",
  "Viridis",
  "YlGnBu",
  "YlOrRd",
  "Custom...",
];

export default function HeatmapColorsSettings({ options, onOptionsChange }: any) {
  return (
    <React.Fragment>
      <Section>
        <Select
          label="Color Scheme"
          data-test="Chart.Colors.Heatmap.ColorScheme"
          placeholder="Choose Color Scheme..."
          allowClear
          value={options.colorScheme || undefined}
          onChange={(value: any) => onOptionsChange({ colorScheme: value || null })}
        >
          {map(ColorSchemes, (scheme) => (
            <Select.Option key={scheme} value={scheme} data-test={`Chart.Colors.Heatmap.ColorScheme.${scheme}`}>
              {scheme}
            </Select.Option>
          ))}
        </Select>
      </Section>

      {/*
        Where the colour scale starts.

        From the data by default, because anchored at zero a grid of values
        between 980 and 1000 comes out one flat colour and says nothing. On,
        for the case where zero is meaningful -- counts, where an empty cell
        should read as empty rather than as "the lowest of these".
      */}
      <Section>
        {/* @ts-expect-error ts-migrate(2745) FIXME: This JSX tag's 'children' prop expects type 'never... Remove this comment to see the full error message */}
        <Switch
          // @ts-expect-error ts-migrate(2322) FIXME: Type 'string' is not assignable to type 'never'.
          id="chart-editor-heatmap-from-zero"
          data-test="Chart.Colors.Heatmap.FromZero"
          // @ts-expect-error ts-migrate(2322) FIXME: Type 'any' is not assignable to type 'never'.
          defaultChecked={options.heatmapFromZero}
          // @ts-expect-error ts-migrate(2322) FIXME: Type '(heatmapFromZero: any) => any' is not assign... Remove this comment to see the full error message
          onChange={(heatmapFromZero: any) => onOptionsChange({ heatmapFromZero })}
        >
          Start the colour scale at zero
        </Switch>
      </Section>

      {options.colorScheme === "Custom..." && (
        <React.Fragment>
          <Section>
            <ColorPicker
              layout="horizontal"
              label="Min Color:"
              data-test="Chart.Colors.Heatmap.MinColor"
              interactive
              placement="topLeft"
              presetColors={ColorPalette}
              color={options.heatMinColor}
              onChange={(heatMinColor: any) => onOptionsChange({ heatMinColor })}
              // @ts-expect-error ts-migrate(2339) FIXME: Property 'Label' does not exist on type '({ classN... Remove this comment to see the full error message
              addonAfter={<ColorPicker.Label color={options.heatMinColor} presetColors={ColorPalette} />}
            />
          </Section>
          <Section>
            <ColorPicker
              layout="horizontal"
              label="Max Color:"
              data-test="Chart.Colors.Heatmap.MaxColor"
              interactive
              placement="topRight"
              presetColors={ColorPalette}
              color={options.heatMaxColor}
              onChange={(heatMaxColor: any) => onOptionsChange({ heatMaxColor })}
              // @ts-expect-error ts-migrate(2339) FIXME: Property 'Label' does not exist on type '({ classN... Remove this comment to see the full error message
              addonAfter={<ColorPicker.Label color={options.heatMaxColor} presetColors={ColorPalette} />}
            />
          </Section>
        </React.Fragment>
      )}
    </React.Fragment>
  );
}

HeatmapColorsSettings.propTypes = EditorPropTypes;
