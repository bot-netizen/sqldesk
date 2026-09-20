import React from "react";
import createTabbedEditor, { UpdateOptionsStrategy } from "@/components/visualizations/editor/createTabbedEditor";
import { Section, InputNumber, Checkbox, ControlLabel } from "@/components/visualizations/editor";
import AntSelect from "antd/lib/select";
import { ValueFormatSection } from "../shared/valueOptions/editor";
import { ColumnSelect } from "../shared/editorControls";

function GeneralSettings({ options, data, onOptionsChange }: any) {
  const columns = data.columns || [];
  const names = new Set(columns.map((c: any) => c.name));
  options.pathColumns.forEach((name: string) => names.add(name));

  return (
    <React.Fragment>
      <Section>
        <ControlLabel label="Group by">
          <AntSelect
            mode="multiple"
            className="w-100"
            value={options.pathColumns}
            placeholder="Outermost level first"
            data-test="Treemap.PathColumns"
            aria-label="Group by"
            // shallowMerge, not the default deep merge, which would union the
            // old list with the new one and make removing a level impossible.
            onChange={(pathColumns: any) =>
              onOptionsChange({ pathColumns: [...pathColumns] }, UpdateOptionsStrategy.shallowMerge)
            }
          >
            {[...names].map((name: any) => (
              <AntSelect.Option key={name} value={name} data-test={`Treemap.PathColumns.${name}`}>
                {name}
              </AntSelect.Option>
            ))}
          </AntSelect>
        </ControlLabel>
      </Section>

      <Section>
        <ColumnSelect
          label="Size column"
          value={options.valueColumn}
          columns={columns}
          onChange={(valueColumn) => onOptionsChange({ valueColumn })}
          data-test="Treemap.ValueColumn"
        />
      </Section>

      {options.pathColumns.length > 1 && (
        <Section>
          <InputNumber
            layout="horizontal"
            label="Levels shown at once"
            min={1}
            max={4}
            value={options.visibleDepth}
            data-test="Treemap.VisibleDepth"
            onChange={(visibleDepth: any) =>
              onOptionsChange({ visibleDepth: Number(visibleDepth) || 1 }, UpdateOptionsStrategy.shallowMerge)
            }
          />
        </Section>
      )}

      <Section>
        <Checkbox
          checked={options.showValues}
          data-test="Treemap.ShowValues"
          onChange={(event: any) =>
            onOptionsChange({ showValues: event.target.checked }, UpdateOptionsStrategy.shallowMerge)
          }
        >
          Write the size under each name
        </Checkbox>
      </Section>

      <Section>
        <Checkbox
          checked={options.showBreadcrumb}
          data-test="Treemap.ShowBreadcrumb"
          onChange={(event: any) =>
            onOptionsChange({ showBreadcrumb: event.target.checked }, UpdateOptionsStrategy.shallowMerge)
          }
        >
          Show the trail when drilling in
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
      sampleValue={first ? first[options.valueColumn] : undefined}
      testPrefix="Treemap.Format"
      onChange={(valueFormat) => onOptionsChange({ valueFormat }, UpdateOptionsStrategy.shallowMerge)}
    />
  );
}

export default createTabbedEditor([
  { key: "General", title: "General", component: GeneralSettings },
  { key: "Format", title: "Format", component: FormatSettings },
]);
