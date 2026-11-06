import React from "react";
import { Section, Select, ControlLabel } from "@/components/visualizations/editor";
import { UpdateOptionsStrategy } from "@/components/visualizations/editor/createTabbedEditor";
import { ValueFormatSection, ColorSelect } from "../shared/valueOptions/editor";

/*
  Four numbers in the order a candle is read, each named rather than
  guessed from column position once the chart is on screen: a query that
  selects high before low draws a candle inside out, and nothing about the
  picture says which way round it went.
*/
const PARTS: [keyof any, string][] = [
  ["openColumn", "Open"],
  ["closeColumn", "Close"],
  ["lowColumn", "Low"],
  ["highColumn", "High"],
];

export default function Editor({ options, data, onOptionsChange }: any) {
  const names = ((data && data.columns) || []).map((column: any) => column.name);

  const pick = (key: string, label: string) => (
    <Section key={key}>
      <Select
        label={label}
        data-test={`Candlestick.${key}`}
        value={options[key]}
        onChange={(value: string) => onOptionsChange({ [key]: value })}
      >
        {names.map((name: string) => (
          <Select.Option key={name} value={name} data-test={`Candlestick.${key}.${name}`}>
            {name}
          </Select.Option>
        ))}
      </Select>
    </Section>
  );

  return (
    <React.Fragment>
      {pick("xColumn", "Axis")}
      {PARTS.map(([key, label]) => pick(key as string, label))}

      <Section>
        <ControlLabel label="Rising">
          <ColorSelect
            value={options.risingColor}
            data-test="Candlestick.RisingColor"
            aria-label="Colour for a rising candle"
            onChange={(risingColor: string) => onOptionsChange({ risingColor })}
          />
        </ControlLabel>
      </Section>
      <Section>
        <ControlLabel label="Falling">
          <ColorSelect
            value={options.fallingColor}
            data-test="Candlestick.FallingColor"
            aria-label="Colour for a falling candle"
            onChange={(fallingColor: string) => onOptionsChange({ fallingColor })}
          />
        </ControlLabel>
      </Section>

      <ValueFormatSection
        format={options.valueFormat}
        sampleValue={((data && data.rows) || [])[0]?.[options.closeColumn]}
        testPrefix="Candlestick.Format"
        onChange={(valueFormat: any) => onOptionsChange({ valueFormat }, UpdateOptionsStrategy.shallowMerge)}
      />
    </React.Fragment>
  );
}
