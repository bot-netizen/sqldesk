import React from "react";
import createTabbedEditor, { UpdateOptionsStrategy } from "@/components/visualizations/editor/createTabbedEditor";
import { Section, Select, Checkbox, ControlLabel } from "@/components/visualizations/editor";
import AntSelect from "antd/lib/select";
import { ValueFormatSection } from "../shared/valueOptions/editor";
import { ColumnSelect } from "../shared/editorControls";
import { numericColumns } from "../shared/rows";

function GeneralSettings({ options, data, onOptionsChange }: any) {
  const columns = data.columns || [];
  const numeric = numericColumns(columns, data.rows || []);
  // Columns already chosen stay on the list even if this result's sample does
  // not look numeric -- a query that returns no rows should not silently drop
  // a saved radar's spokes.
  const names = new Set(numeric.map((c: any) => c.name));
  options.valueColumns.forEach((name: string) => names.add(name));

  return (
    <React.Fragment>
      <Section>
        <ColumnSelect
          label="Name column"
          value={options.labelColumn}
          columns={columns}
          noneLabel="Number the rows"
          onChange={(labelColumn) => onOptionsChange({ labelColumn })}
          data-test="Radar.LabelColumn"
        />
      </Section>

      <Section>
        <ControlLabel label="Measures">
          <AntSelect
            mode="multiple"
            className="w-100"
            value={options.valueColumns}
            placeholder="Pick at least three"
            data-test="Radar.ValueColumns"
            aria-label="Measures"
            // shallowMerge, not the default deep merge: a deep merge unions
            // the old array with the new one element by element, so removing a
            // measure would never take effect.
            onChange={(valueColumns: any) =>
              onOptionsChange({ valueColumns: [...valueColumns] }, UpdateOptionsStrategy.shallowMerge)
            }
          >
            {[...names].map((name) => (
              <AntSelect.Option key={name} value={name} data-test={`Radar.ValueColumns.${name}`}>
                {name}
              </AntSelect.Option>
            ))}
          </AntSelect>
        </ControlLabel>
      </Section>

      <Section>
        <Select
          layout="horizontal"
          label="Spoke scales"
          value={options.scaleMode}
          data-test="Radar.ScaleMode"
          onChange={(scaleMode: any) => onOptionsChange({ scaleMode })}
        >
          <Select.Option value="per-spoke" data-test="Radar.ScaleMode.per-spoke">
            Each its own, for mixed units
          </Select.Option>
          <Select.Option value="shared" data-test="Radar.ScaleMode.shared">
            One shared, for the same units
          </Select.Option>
        </Select>
      </Section>

      <Section>
        <Select
          layout="horizontal"
          label="Web shape"
          value={options.shape}
          data-test="Radar.Shape"
          onChange={(shape: any) => onOptionsChange({ shape })}
        >
          <Select.Option value="polygon" data-test="Radar.Shape.polygon">
            Polygon
          </Select.Option>
          <Select.Option value="circle" data-test="Radar.Shape.circle">
            Circle
          </Select.Option>
        </Select>
      </Section>

      <Section>
        <Checkbox
          checked={options.showArea}
          data-test="Radar.ShowArea"
          onChange={(event: any) =>
            onOptionsChange({ showArea: event.target.checked }, UpdateOptionsStrategy.shallowMerge)
          }
        >
          Fill each shape
        </Checkbox>
      </Section>

      <Section>
        <Checkbox
          checked={options.showLegend}
          data-test="Radar.ShowLegend"
          onChange={(event: any) =>
            onOptionsChange({ showLegend: event.target.checked }, UpdateOptionsStrategy.shallowMerge)
          }
        >
          Show the legend
        </Checkbox>
      </Section>
    </React.Fragment>
  );
}

function FormatSettings({ options, data, onOptionsChange }: any) {
  const first = (data.rows || [])[0];
  const sampleColumn = options.valueColumns[0];
  return (
    <ValueFormatSection
      format={options.valueFormat}
      sampleValue={first && sampleColumn ? first[sampleColumn] : undefined}
      testPrefix="Radar.Format"
      onChange={(valueFormat) => onOptionsChange({ valueFormat }, UpdateOptionsStrategy.shallowMerge)}
    />
  );
}

export default createTabbedEditor([
  { key: "General", title: "General", component: GeneralSettings },
  { key: "Format", title: "Format", component: FormatSettings },
]);
