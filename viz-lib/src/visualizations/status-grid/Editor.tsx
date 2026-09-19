import React from "react";
import createTabbedEditor, { UpdateOptionsStrategy } from "@/components/visualizations/editor/createTabbedEditor";
import { Section, Select } from "@/components/visualizations/editor";
import { ValueFormatSection, ThresholdsSection, ValueMappingsSection } from "../shared/valueOptions/editor";
import { ColumnSelect } from "../shared/editorControls";

function GeneralSettings({ options, data, onOptionsChange }: any) {
  const columns = data.columns || [];
  return (
    <React.Fragment>
      {/* @ts-expect-error Section's children type is too narrow in its declaration */}
      <Section>
        <ColumnSelect
          label="Name column"
          value={options.nameColumn}
          columns={columns}
          noneLabel="Number the rows"
          onChange={(nameColumn) => onOptionsChange({ nameColumn })}
          data-test="StatusGrid.NameColumn"
        />
      </Section>
      {/* @ts-expect-error Section's children type is too narrow in its declaration */}
      <Section>
        <ColumnSelect
          label="Value column"
          value={options.valueColumn}
          columns={columns}
          noneLabel="None"
          onChange={(valueColumn) => onOptionsChange({ valueColumn })}
          data-test="StatusGrid.ValueColumn"
        />
      </Section>
      {/* @ts-expect-error Section's children type is too narrow in its declaration */}
      <Section>
        <ColumnSelect
          label="Status column"
          value={options.statusColumn}
          columns={columns}
          noneLabel="None: colour by the value's thresholds"
          onChange={(statusColumn) => onOptionsChange({ statusColumn })}
          data-test="StatusGrid.StatusColumn"
        />
      </Section>
      {/* @ts-expect-error Section's children type is too narrow in its declaration */}
      <Section>
        <ColumnSelect
          label="Detail column"
          value={options.detailColumn}
          columns={columns}
          noneLabel="None"
          onChange={(detailColumn) => onOptionsChange({ detailColumn })}
          data-test="StatusGrid.DetailColumn"
        />
      </Section>
      {/* @ts-expect-error Section's children type is too narrow in its declaration */}
      <Section>
        <Select
          layout="horizontal"
          label="Tile size"
          value={options.tileSize}
          data-test="StatusGrid.TileSize"
          onChange={(tileSize: any) => onOptionsChange({ tileSize })}
        >
          {/* @ts-expect-error Select.Option is added by withControlLabel's wrapped component */}
          <Select.Option value="small">Small</Select.Option>
          {/* @ts-expect-error see above */}
          <Select.Option value="medium">Medium</Select.Option>
          {/* @ts-expect-error see above */}
          <Select.Option value="large">Large</Select.Option>
        </Select>
      </Section>
      {/* @ts-expect-error Section's children type is too narrow in its declaration */}
      <Section>
        <Select
          layout="horizontal"
          label="Order"
          value={options.sort}
          data-test="StatusGrid.Sort"
          onChange={(sort: any) => onOptionsChange({ sort })}
        >
          {/* @ts-expect-error Select.Option is added by withControlLabel's wrapped component */}
          <Select.Option value="none">As the query returns them</Select.Option>
          {/* @ts-expect-error see above */}
          <Select.Option value="severity">Worst first</Select.Option>
          {/* @ts-expect-error see above */}
          <Select.Option value="name">By name</Select.Option>
        </Select>
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
      testPrefix="StatusGrid.Format"
      onChange={(valueFormat) => onOptionsChange({ valueFormat }, UpdateOptionsStrategy.shallowMerge)}
    />
  );
}

function ColourSettings({ options, onOptionsChange }: any) {
  return (
    <React.Fragment>
      <ValueMappingsSection
        mappings={options.mappings}
        testPrefix="StatusGrid"
        description="Status text to colour, ignoring case. Common words are already mapped. A mapping can also change what the tile says."
        onChange={(mappings) => onOptionsChange({ mappings }, UpdateOptionsStrategy.shallowMerge)}
      />
      <ThresholdsSection
        thresholds={options.thresholds}
        testPrefix="StatusGrid"
        description="Used for the value column when no status mapping applies."
        onChange={(thresholds) => onOptionsChange({ thresholds }, UpdateOptionsStrategy.shallowMerge)}
      />
    </React.Fragment>
  );
}

export default createTabbedEditor([
  { key: "General", title: "General", component: GeneralSettings },
  { key: "Format", title: "Format", component: FormatSettings },
  { key: "Colours", title: "Colours", component: ColourSettings },
]);
