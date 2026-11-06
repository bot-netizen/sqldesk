import React from "react";
import { Section, Select, Checkbox } from "@/components/visualizations/editor";
import { UpdateOptionsStrategy } from "@/components/visualizations/editor/createTabbedEditor";
import { ValueFormatSection } from "../shared/valueOptions/editor";

export default function Editor({ options, data, onOptionsChange }: any) {
  const names = ((data && data.columns) || []).map((column: any) => column.name);

  const pick = (key: string, label: string, allowNone = false) => (
    <Section key={key}>
      <Select
        label={label}
        data-test={`Network.${key}`}
        value={options[key]}
        onChange={(value: string) => onOptionsChange({ [key]: value })}
      >
        {allowNone && (
          <Select.Option key="" value="" data-test={`Network.${key}.none`}>
            Every connection weighs the same
          </Select.Option>
        )}
        {names.map((name: string) => (
          <Select.Option key={name} value={name} data-test={`Network.${key}.${name}`}>
            {name}
          </Select.Option>
        ))}
      </Select>
    </Section>
  );

  return (
    <React.Fragment>
      {pick("sourceColumn", "From")}
      {pick("targetColumn", "To")}
      {pick("valueColumn", "Weight", true)}

      <Section>
        <Checkbox
          data-test="Network.Directed"
          checked={!!options.directed}
          onChange={(event: any) => onOptionsChange({ directed: event.target.checked })}
        >
          Connections have a direction
        </Checkbox>
      </Section>

      <Section>
        <Checkbox
          data-test="Network.SizeByWeight"
          checked={options.sizeByWeight !== false}
          onChange={(event: any) => onOptionsChange({ sizeByWeight: event.target.checked })}
        >
          Size each node by what flows through it
        </Checkbox>
      </Section>

      <Section>
        <Checkbox
          data-test="Network.ShowLabels"
          checked={options.showLabels !== false}
          onChange={(event: any) => onOptionsChange({ showLabels: event.target.checked })}
        >
          Show names
        </Checkbox>
      </Section>

      <ValueFormatSection
        format={options.valueFormat}
        sampleValue={((data && data.rows) || [])[0]?.[options.valueColumn]}
        testPrefix="Network.Format"
        onChange={(valueFormat: any) => onOptionsChange({ valueFormat }, UpdateOptionsStrategy.shallowMerge)}
      />
    </React.Fragment>
  );
}
