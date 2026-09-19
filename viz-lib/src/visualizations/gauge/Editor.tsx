import React from "react";
import createTabbedEditor, { UpdateOptionsStrategy } from "@/components/visualizations/editor/createTabbedEditor";
import { Section, Select, Input, InputNumber } from "@/components/visualizations/editor";
import { ValueFormatSection, ThresholdsSection } from "../shared/valueOptions/editor";
import { ColumnSelect } from "../shared/editorControls";
import { pickRow } from "../shared/rows";

function numberOrNull(v: any): number | null {
  if (v === null || v === undefined || v === "") {
    return null;
  }
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function GeneralSettings({ options, data, onOptionsChange }: any) {
  const columns = data.columns || [];
  return (
    <React.Fragment>
      <Section>
        <Select
          layout="horizontal"
          label="Style"
          value={options.style}
          data-test="Gauge.Style"
          onChange={(style: any) => onOptionsChange({ style })}
        >
          <Select.Option value="needle" data-test="Gauge.Style.needle">
            Needle
          </Select.Option>
          <Select.Option value="ring" data-test="Gauge.Style.ring">
            Progress ring
          </Select.Option>
          <Select.Option value="half" data-test="Gauge.Style.half">
            Half arc
          </Select.Option>
        </Select>
      </Section>

      <Section>
        <ColumnSelect
          label="Value column"
          value={options.valueColumn}
          columns={columns}
          onChange={(valueColumn) => onOptionsChange({ valueColumn })}
          data-test="Gauge.ValueColumn"
        />
      </Section>

      <Section>
        <InputNumber
          layout="horizontal"
          label="Row"
          value={options.rowNumber}
          data-test="Gauge.RowNumber"
          onChange={(rowNumber: any) => onOptionsChange({ rowNumber: numberOrNull(rowNumber) ?? 1 })}
        />
        <p className="value-options-help">1 is the first row, -1 the last.</p>
      </Section>

      <Section>
        <Input
          layout="horizontal"
          label="Label"
          value={options.label}
          placeholder={options.valueColumn}
          data-test="Gauge.Label"
          onChange={(e: any) => onOptionsChange({ label: e.target.value })}
        />
      </Section>

      <Section>
        <InputNumber
          layout="horizontal"
          label="Minimum"
          value={options.min}
          disabled={!!options.minColumn}
          data-test="Gauge.Min"
          onChange={(min: any) => onOptionsChange({ min: numberOrNull(min) ?? 0 })}
        />
      </Section>
      <Section>
        <ColumnSelect
          label="…or from column"
          value={options.minColumn}
          columns={columns}
          noneLabel="Use the number above"
          onChange={(minColumn) => onOptionsChange({ minColumn })}
          data-test="Gauge.MinColumn"
        />
      </Section>

      <Section>
        <InputNumber
          layout="horizontal"
          label="Maximum"
          value={options.max}
          disabled={!!options.maxColumn}
          data-test="Gauge.Max"
          onChange={(max: any) => onOptionsChange({ max: numberOrNull(max) ?? 100 })}
        />
      </Section>
      <Section>
        <ColumnSelect
          label="…or from column"
          value={options.maxColumn}
          columns={columns}
          noneLabel="Use the number above"
          onChange={(maxColumn) => onOptionsChange({ maxColumn })}
          data-test="Gauge.MaxColumn"
        />
      </Section>

      <Section>
        <InputNumber
          layout="horizontal"
          label="Target"
          value={options.target === null ? undefined : options.target}
          placeholder="None"
          disabled={!!options.targetColumn}
          data-test="Gauge.Target"
          // Replaced, not merged: clearing the field has to be able to store null.
          onChange={(target: any) =>
            onOptionsChange({ target: numberOrNull(target) }, UpdateOptionsStrategy.shallowMerge)
          }
        />
      </Section>
      <Section>
        <ColumnSelect
          label="…or from column"
          value={options.targetColumn}
          columns={columns}
          noneLabel="Use the number above"
          onChange={(targetColumn) => onOptionsChange({ targetColumn })}
          data-test="Gauge.TargetColumn"
        />
      </Section>
    </React.Fragment>
  );
}

function FormatSettings({ options, data, onOptionsChange }: any) {
  const row = pickRow<any>(data.rows || [], options.rowNumber);
  return (
    <ValueFormatSection
      format={options.valueFormat}
      sampleValue={row ? row[options.valueColumn] : undefined}
      testPrefix="Gauge.Format"
      onChange={(valueFormat) => onOptionsChange({ valueFormat }, UpdateOptionsStrategy.shallowMerge)}
    />
  );
}

function ThresholdSettings({ options, onOptionsChange }: any) {
  return (
    <ThresholdsSection
      thresholds={options.thresholds}
      testPrefix="Gauge"
      description="Colour the arc in bands. The needle style draws every band; the ring and half arc take the colour of the band the value is in."
      onChange={(thresholds) => onOptionsChange({ thresholds }, UpdateOptionsStrategy.shallowMerge)}
    />
  );
}

export default createTabbedEditor([
  { key: "General", title: "General", component: GeneralSettings },
  { key: "Format", title: "Format", component: FormatSettings },
  { key: "Thresholds", title: "Thresholds", component: ThresholdSettings },
]);
