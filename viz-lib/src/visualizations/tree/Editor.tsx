import React from "react";
import { Section, Select, Checkbox, InputNumber } from "@/components/visualizations/editor";
import { UpdateOptionsStrategy } from "@/components/visualizations/editor/createTabbedEditor";
import { ValueFormatSection } from "../shared/valueOptions/editor";

export default function Editor({ options, data, onOptionsChange }: any) {
  const names = ((data && data.columns) || []).map((column: any) => column.name);

  return (
    <React.Fragment>
      <Section>
        <Select
          label="Hierarchy"
          data-test="Tree.PathColumns"
          mode="multiple"
          value={options.pathColumns}
          onChange={(pathColumns: string[]) => onOptionsChange({ pathColumns })}
        >
          {names.map((name: string) => (
            <Select.Option key={name} value={name} data-test={`Tree.PathColumns.${name}`}>
              {name}
            </Select.Option>
          ))}
        </Select>
      </Section>

      <Section>
        <Select
          label="Value"
          data-test="Tree.ValueColumn"
          value={options.valueColumn}
          onChange={(valueColumn: string) => onOptionsChange({ valueColumn })}
        >
          {names.map((name: string) => (
            <Select.Option key={name} value={name} data-test={`Tree.ValueColumn.${name}`}>
              {name}
            </Select.Option>
          ))}
        </Select>
      </Section>

      <Section>
        <Select
          label="Direction"
          data-test="Tree.Layout"
          value={options.layout}
          onChange={(layout: string) => onOptionsChange({ layout })}
        >
          <Select.Option value="horizontal" data-test="Tree.Layout.horizontal">
            Left to right
          </Select.Option>
          <Select.Option value="vertical" data-test="Tree.Layout.vertical">
            Top down
          </Select.Option>
          <Select.Option value="radial" data-test="Tree.Layout.radial">
            Radial
          </Select.Option>
        </Select>
      </Section>

      <Section>
        <InputNumber
          label="Open to depth"
          data-test="Tree.InitialDepth"
          min={1}
          max={6}
          value={options.initialDepth}
          onChange={(initialDepth: any) => onOptionsChange({ initialDepth })}
        />
      </Section>

      <Section>
        <Checkbox
          data-test="Tree.ShowValues"
          checked={!!options.showValues}
          onChange={(event: any) => onOptionsChange({ showValues: event.target.checked })}
        >
          Show each value
        </Checkbox>
      </Section>

      <ValueFormatSection
        format={options.valueFormat}
        sampleValue={((data && data.rows) || [])[0]?.[options.valueColumn]}
        testPrefix="Tree.Format"
        onChange={(valueFormat: any) => onOptionsChange({ valueFormat }, UpdateOptionsStrategy.shallowMerge)}
      />
    </React.Fragment>
  );
}
