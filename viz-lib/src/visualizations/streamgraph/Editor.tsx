import React from "react";
import { Section, Select, Checkbox } from "@/components/visualizations/editor";
import { ValueFormatSection } from "../shared/valueOptions/editor";
import { UpdateOptionsStrategy } from "@/components/visualizations/editor/createTabbedEditor";

export default function Editor({ options, data, onOptionsChange }: any) {
  const columns = (data && data.columns) || [];
  const names = columns.map((column: any) => column.name);

  return (
    <React.Fragment>
      <Section>
        <Select
          label="Axis"
          data-test="Streamgraph.XColumn"
          value={options.xColumn}
          onChange={(xColumn: string) => onOptionsChange({ xColumn })}
        >
          {names.map((name: string) => (
            <Select.Option key={name} value={name} data-test={`Streamgraph.XColumn.${name}`}>
              {name}
            </Select.Option>
          ))}
        </Select>
      </Section>

      <Section>
        <Select
          label="Bands"
          data-test="Streamgraph.SeriesColumn"
          value={options.seriesColumn}
          onChange={(seriesColumn: string) => onOptionsChange({ seriesColumn })}
        >
          {names.map((name: string) => (
            <Select.Option key={name} value={name} data-test={`Streamgraph.SeriesColumn.${name}`}>
              {name}
            </Select.Option>
          ))}
        </Select>
      </Section>

      <Section>
        <Select
          label="Value"
          data-test="Streamgraph.ValueColumn"
          value={options.valueColumn}
          onChange={(valueColumn: string) => onOptionsChange({ valueColumn })}
        >
          {names.map((name: string) => (
            <Select.Option key={name} value={name} data-test={`Streamgraph.ValueColumn.${name}`}>
              {name}
            </Select.Option>
          ))}
        </Select>
      </Section>

      <Section>
        <Checkbox
          data-test="Streamgraph.ShowLegend"
          checked={options.showLegend !== false}
          onChange={(event: any) => onOptionsChange({ showLegend: event.target.checked })}
        >
          Show legend
        </Checkbox>
      </Section>

      <ValueFormatSection
        format={options.valueFormat}
        sampleValue={((data && data.rows) || [])[0]?.[options.valueColumn]}
        testPrefix="Streamgraph.Format"
        onChange={(valueFormat: any) => onOptionsChange({ valueFormat }, UpdateOptionsStrategy.shallowMerge)}
      />
    </React.Fragment>
  );
}
