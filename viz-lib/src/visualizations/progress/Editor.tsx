import React from "react";
import createTabbedEditor, { UpdateOptionsStrategy } from "@/components/visualizations/editor/createTabbedEditor";
import { Section, Select, InputNumber } from "@/components/visualizations/editor";
import { ValueFormatSection, ThresholdsSection } from "../shared/valueOptions/editor";
import { ColumnSelect } from "../shared/editorControls";

function numberOrNull(v: any): number | null {
  if (v === null || v === undefined || v === "") {
    return null;
  }
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function GeneralSettings({ options, data, onOptionsChange }: any) {
  const columns = data.columns || [];
  const hasTarget = !!options.targetColumn || options.target !== null;
  return (
    <React.Fragment>
      {/* @ts-expect-error Section's children type is too narrow in its declaration */}
      <Section>
        <Select
          layout="horizontal"
          label="Style"
          value={options.mode}
          data-test="Progress.Mode"
          onChange={(mode: any) => onOptionsChange({ mode })}
        >
          {/* @ts-expect-error Select.Option is added by withControlLabel's wrapped component */}
          <Select.Option value="bullet" data-test="Progress.Mode.bullet">
            Bullet: bar over graded bands, with a target tick
            {/* @ts-expect-error see above */}
          </Select.Option>
          {/* @ts-expect-error see above */}
          <Select.Option value="bar" data-test="Progress.Mode.bar">
            Progress bar: a filled track
            {/* @ts-expect-error see above */}
          </Select.Option>
        </Select>
      </Section>

      {/* @ts-expect-error Section's children type is too narrow in its declaration */}
      <Section>
        <ColumnSelect
          label="Label column"
          value={options.labelColumn}
          columns={columns}
          noneLabel="Number the rows"
          onChange={(labelColumn) => onOptionsChange({ labelColumn })}
          data-test="Progress.LabelColumn"
        />
      </Section>

      {/* @ts-expect-error Section's children type is too narrow in its declaration */}
      <Section>
        <ColumnSelect
          label="Value column"
          value={options.valueColumn}
          columns={columns}
          onChange={(valueColumn) => onOptionsChange({ valueColumn })}
          data-test="Progress.ValueColumn"
        />
      </Section>

      {/* @ts-expect-error Section's children type is too narrow in its declaration */}
      <Section>
        <ColumnSelect
          label="Target column"
          value={options.targetColumn}
          columns={columns}
          noneLabel="One target for every row"
          onChange={(targetColumn) => onOptionsChange({ targetColumn })}
          data-test="Progress.TargetColumn"
        />
      </Section>

      {!options.targetColumn && (
        // @ts-expect-error Section's children type is too narrow in its declaration
        <Section>
          <InputNumber
            layout="horizontal"
            label="Target"
            placeholder="None"
            value={options.target === null ? undefined : options.target}
            data-test="Progress.Target"
            onChange={(target: any) =>
              onOptionsChange({ target: numberOrNull(target) }, UpdateOptionsStrategy.shallowMerge)
            }
          />
        </Section>
      )}

      {!hasTarget && (
        // @ts-expect-error Section's children type is too narrow in its declaration
        <Section>
          <InputNumber
            layout="horizontal"
            label="Scale maximum"
            placeholder="Largest value"
            value={options.max === null ? undefined : options.max}
            data-test="Progress.Max"
            onChange={(max: any) => onOptionsChange({ max: numberOrNull(max) }, UpdateOptionsStrategy.shallowMerge)}
          />
        </Section>
      )}
    </React.Fragment>
  );
}

function FormatSettings({ options, data, onOptionsChange }: any) {
  const first = (data.rows || [])[0];
  return (
    <ValueFormatSection
      format={options.valueFormat}
      sampleValue={first ? first[options.valueColumn] : undefined}
      testPrefix="Progress.Format"
      onChange={(valueFormat) => onOptionsChange({ valueFormat }, UpdateOptionsStrategy.shallowMerge)}
    />
  );
}

function ThresholdSettings({ options, onOptionsChange }: any) {
  const hasTarget = !!options.targetColumn || options.target !== null;
  return (
    <ThresholdsSection
      thresholds={options.thresholds}
      testPrefix="Progress"
      description={
        hasTarget
          ? "Values are percent of target: 70 means 70% of the way there. The bullet style also draws these as the bands behind each bar."
          : "Values are in the value column's own units. The bullet style also draws these as the bands behind each bar."
      }
      onChange={(thresholds) => onOptionsChange({ thresholds }, UpdateOptionsStrategy.shallowMerge)}
    />
  );
}

export default createTabbedEditor([
  { key: "General", title: "General", component: GeneralSettings },
  { key: "Format", title: "Format", component: FormatSettings },
  { key: "Thresholds", title: "Thresholds", component: ThresholdSettings },
]);
