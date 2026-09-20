import React from "react";
import createTabbedEditor, { UpdateOptionsStrategy } from "@/components/visualizations/editor/createTabbedEditor";
import { Section, Select, Checkbox, ControlLabel } from "@/components/visualizations/editor";
import { ValueFormatSection, ColorSelect } from "../shared/valueOptions/editor";
import { ColumnSelect } from "../shared/editorControls";

function GeneralSettings({ options, data, onOptionsChange }: any) {
  const columns = data.columns || [];
  return (
    <React.Fragment>
      <Section>
        <ColumnSelect
          label="Date column"
          value={options.dateColumn}
          columns={columns}
          onChange={(dateColumn) => onOptionsChange({ dateColumn })}
          data-test="Calendar.DateColumn"
        />
      </Section>

      <Section>
        <ColumnSelect
          label="Value column"
          value={options.valueColumn}
          columns={columns}
          noneLabel="Count the rows"
          onChange={(valueColumn) => onOptionsChange({ valueColumn })}
          data-test="Calendar.ValueColumn"
        />
      </Section>

      <Section>
        <Select
          layout="horizontal"
          label="Show"
          value={options.range}
          data-test="Calendar.Range"
          onChange={(range: any) => onOptionsChange({ range })}
        >
          <Select.Option value="3-months" data-test="Calendar.Range.3-months">
            The last three months
          </Select.Option>
          <Select.Option value="12-months" data-test="Calendar.Range.12-months">
            The last twelve months
          </Select.Option>
          <Select.Option value="year" data-test="Calendar.Range.year">
            The whole calendar year
          </Select.Option>
          <Select.Option value="all" data-test="Calendar.Range.all">
            Everything the query returned
          </Select.Option>
        </Select>
      </Section>

      <Section>
        <ControlLabel label="Busiest day">
          <ColorSelect
            value={options.color}
            data-test="Calendar.Color"
            aria-label="Busiest day colour"
            onChange={(color) => onOptionsChange({ color }, UpdateOptionsStrategy.shallowMerge)}
          />
        </ControlLabel>
      </Section>

      <Section>
        <Checkbox
          checked={options.startOnMonday}
          data-test="Calendar.StartOnMonday"
          onChange={(event: any) =>
            onOptionsChange({ startOnMonday: event.target.checked }, UpdateOptionsStrategy.shallowMerge)
          }
        >
          Weeks start on Monday
        </Checkbox>
      </Section>
    </React.Fragment>
  );
}

function FormatSettings({ options, data, onOptionsChange }: any) {
  const first = (data.rows || [])[0];
  return (
    <ValueFormatSection
      format={options.valueFormat}
      sampleValue={first && options.valueColumn ? first[options.valueColumn] : undefined}
      testPrefix="Calendar.Format"
      onChange={(valueFormat) => onOptionsChange({ valueFormat }, UpdateOptionsStrategy.shallowMerge)}
    />
  );
}

export default createTabbedEditor([
  { key: "General", title: "General", component: GeneralSettings },
  { key: "Format", title: "Format", component: FormatSettings },
]);
