import React from "react";
import { Section, Select, Checkbox } from "@/components/visualizations/editor";
import { ThresholdsSection, ValueMappingsSection, ColorSelect } from "../../shared/valueOptions/editor";
import { normalizeCellFormat, CellFormat } from "../cellFormat";

type Props = {
  column: any;
  onChange: (column: any) => void;
};

export default function CellFormatSection({ column, onChange }: Props) {
  const f = normalizeCellFormat(column.cellFormat);
  const prefix = `Table.Column.${column.name}.CellFormat`;
  const numeric = column.displayAs === "number";
  const update = (changes: Partial<CellFormat>) => onChange({ ...column, cellFormat: { ...f, ...changes } });

  return (
    <div className="table-visualization-editor-cell-format" data-test={prefix}>
      <Section>
        <Select
          label="Colour cells"
          value={f.color}
          data-test={`${prefix}.Color`}
          onChange={(color: any) => update({ color })}
        >
          <Select.Option value="none" data-test={`${prefix}.Color.none`}>
            No
          </Select.Option>
          <Select.Option value="rules" data-test={`${prefix}.Color.rules`}>
            {numeric ? "By thresholds" : "By value"}
          </Select.Option>
          {numeric && (
            <Select.Option value="scale" data-test={`${prefix}.Color.scale`}>
              As a scale, lowest to highest
            </Select.Option>
          )}
        </Select>
      </Section>

      {f.color !== "none" && (
        <Section>
          <Select
            label="Colour the"
            value={f.colorTarget}
            data-test={`${prefix}.Target`}
            onChange={(colorTarget: any) => update({ colorTarget })}
          >
            <Select.Option value="background">Cell background</Select.Option>
            <Select.Option value="text">Text</Select.Option>
          </Select>
        </Section>
      )}

      {f.color === "rules" && numeric && (
        <ThresholdsSection
          allowNoneBase
          thresholds={f.rules}
          testPrefix={prefix}
          description="Cells take the colour of the step their value reaches. Leave the base empty to keep lower values plain."
          onChange={(rules) => update({ rules })}
        />
      )}

      {f.color === "rules" && !numeric && (
        <ValueMappingsSection
          mappings={f.mappings}
          testPrefix={prefix}
          description="Cells whose text matches, ignoring case, take the colour. The text can also be replaced."
          onChange={(mappings) => update({ mappings })}
        />
      )}

      {f.color === "scale" && (
        <Section>
          <label className="value-options-help" htmlFor={`${prefix}.ScaleColor`}>
            Colour deepens from the column's lowest value to its highest
          </label>
          <ColorSelect
            value={f.scaleColor}
            onChange={(scaleColor) => update({ scaleColor })}
            data-test={`${prefix}.ScaleColor`}
            aria-label="Scale colour"
          />
        </Section>
      )}

      {numeric && (
        <Section>
          <Checkbox
            data-test={`${prefix}.DataBar`}
            checked={f.dataBar}
            onChange={(event: any) => update({ dataBar: event.target.checked })}
          >
            Data bar behind the number
          </Checkbox>
        </Section>
      )}

      <Section>
        <Checkbox
          data-test={`${prefix}.ShowChange`}
          checked={f.showChange}
          onChange={(event: any) => update({ showChange: event.target.checked })}
        >
          Highlight changes since the last refresh
        </Checkbox>
      </Section>
    </div>
  );
}
