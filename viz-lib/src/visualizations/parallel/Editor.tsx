import React from "react";
import { Section, Select, Checkbox } from "@/components/visualizations/editor";
import { UpdateOptionsStrategy } from "@/components/visualizations/editor/createTabbedEditor";
import { ValueFormatSection } from "../shared/valueOptions/editor";
import { numericColumns } from "../shared/rows";

export default function Editor({ options, data, onOptionsChange }: any) {
  const columns = (data && data.columns) || [];
  const rows = (data && data.rows) || [];
  const numbers = numericColumns(columns, rows).map((column: any) => column.name);
  const names = columns.map((column: any) => column.name);

  return (
    <React.Fragment>
      <Section>
        <Select
          label="Axes"
          data-test="Parallel.DimensionColumns"
          mode="multiple"
          value={options.dimensionColumns}
          onChange={(dimensionColumns: string[]) => onOptionsChange({ dimensionColumns })}
        >
          {numbers.map((name: string) => (
            <Select.Option key={name} value={name} data-test={`Parallel.DimensionColumns.${name}`}>
              {name}
            </Select.Option>
          ))}
        </Select>
      </Section>

      <Section>
        <Select
          label="Colour by"
          data-test="Parallel.SeriesColumn"
          value={options.seriesColumn}
          onChange={(seriesColumn: string) => onOptionsChange({ seriesColumn })}
        >
          <Select.Option key="" value="" data-test="Parallel.SeriesColumn.none">
            One colour for every row
          </Select.Option>
          {names.map((name: string) => (
            <Select.Option key={name} value={name} data-test={`Parallel.SeriesColumn.${name}`}>
              {name}
            </Select.Option>
          ))}
        </Select>
      </Section>

      <Section>
        <Checkbox
          data-test="Parallel.ShowLegend"
          checked={options.showLegend !== false}
          onChange={(event: any) => onOptionsChange({ showLegend: event.target.checked })}
        >
          Show legend
        </Checkbox>
      </Section>

      <ValueFormatSection
        format={options.valueFormat}
        sampleValue={rows[0]?.[(options.dimensionColumns || [])[0]]}
        testPrefix="Parallel.Format"
        onChange={(valueFormat: any) => onOptionsChange({ valueFormat }, UpdateOptionsStrategy.shallowMerge)}
      />
    </React.Fragment>
  );
}
