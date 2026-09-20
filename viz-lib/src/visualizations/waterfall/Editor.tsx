import React from "react";
import createTabbedEditor, { UpdateOptionsStrategy } from "@/components/visualizations/editor/createTabbedEditor";
import { Section, Input, Checkbox, ControlLabel } from "@/components/visualizations/editor";
import { ValueFormatSection, ColorSelect } from "../shared/valueOptions/editor";
import { ColumnSelect } from "../shared/editorControls";

function GeneralSettings({ options, data, onOptionsChange }: any) {
  const columns = data.columns || [];
  return (
    <React.Fragment>
      <Section>
        <ColumnSelect
          label="Step column"
          value={options.labelColumn}
          columns={columns}
          noneLabel="Number the steps"
          onChange={(labelColumn) => onOptionsChange({ labelColumn })}
          data-test="Waterfall.LabelColumn"
        />
      </Section>

      <Section>
        <ColumnSelect
          label="Change column"
          value={options.valueColumn}
          columns={columns}
          onChange={(valueColumn) => onOptionsChange({ valueColumn })}
          data-test="Waterfall.ValueColumn"
        />
      </Section>

      <Section>
        <ColumnSelect
          label="Subtotal column"
          value={options.totalColumn}
          columns={columns}
          noneLabel="No subtotals"
          onChange={(totalColumn) => onOptionsChange({ totalColumn })}
          data-test="Waterfall.TotalColumn"
        />
      </Section>

      <Section>
        <Checkbox
          checked={options.showTotal}
          data-test="Waterfall.ShowTotal"
          onChange={(event: any) =>
            onOptionsChange({ showTotal: event.target.checked }, UpdateOptionsStrategy.shallowMerge)
          }
        >
          Finish with a total bar
        </Checkbox>
      </Section>

      {options.showTotal && (
        <Section>
          <Input
            layout="horizontal"
            label="Total label"
            value={options.totalLabel}
            data-test="Waterfall.TotalLabel"
            onChange={(event: any) =>
              onOptionsChange({ totalLabel: event.target.value }, UpdateOptionsStrategy.shallowMerge)
            }
          />
        </Section>
      )}

      <Section>
        <Checkbox
          checked={options.showValues}
          data-test="Waterfall.ShowValues"
          onChange={(event: any) =>
            onOptionsChange({ showValues: event.target.checked }, UpdateOptionsStrategy.shallowMerge)
          }
        >
          Write each change on its bar
        </Checkbox>
      </Section>

      <Section>
        <Checkbox
          checked={options.showConnectors}
          data-test="Waterfall.ShowConnectors"
          onChange={(event: any) =>
            onOptionsChange({ showConnectors: event.target.checked }, UpdateOptionsStrategy.shallowMerge)
          }
        >
          Link the bars
        </Checkbox>
      </Section>
    </React.Fragment>
  );
}

function ColorSettings({ options, onOptionsChange }: any) {
  const picker = (label: string, key: string, test: string) => (
    <Section>
      <ControlLabel label={label}>
        <ColorSelect
          value={options[key]}
          data-test={test}
          aria-label={label}
          onChange={(color) => onOptionsChange({ [key]: color }, UpdateOptionsStrategy.shallowMerge)}
        />
      </ControlLabel>
    </Section>
  );
  return (
    <React.Fragment>
      {picker("Rises", "riseColor", "Waterfall.RiseColor")}
      {picker("Falls", "fallColor", "Waterfall.FallColor")}
      {picker("Totals", "totalColor", "Waterfall.TotalColor")}
    </React.Fragment>
  );
}

function FormatSettings({ options, data, onOptionsChange }: any) {
  const first = (data.rows || [])[0];
  return (
    <ValueFormatSection
      format={options.valueFormat}
      sampleValue={first ? first[options.valueColumn] : undefined}
      testPrefix="Waterfall.Format"
      onChange={(valueFormat) => onOptionsChange({ valueFormat }, UpdateOptionsStrategy.shallowMerge)}
    />
  );
}

export default createTabbedEditor([
  { key: "General", title: "General", component: GeneralSettings },
  { key: "Colors", title: "Colours", component: ColorSettings },
  { key: "Format", title: "Format", component: FormatSettings },
]);
