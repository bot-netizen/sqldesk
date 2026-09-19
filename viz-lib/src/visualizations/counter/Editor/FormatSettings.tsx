import React from "react";
import { UpdateOptionsStrategy } from "@/components/visualizations/editor/createTabbedEditor";
import { Section, Select, Input, InputNumber, Switch } from "@/components/visualizations/editor";
import { ValueFormatSection } from "../../shared/valueOptions/editor";
import { EditorPropTypes } from "@/visualizations/prop-types";

import { isValueNumber } from "../utils";

function FormatModeSelect({ options, onOptionsChange }: any) {
  return (
    <Section>
      <Select
        layout="horizontal"
        label="Number format"
        value={options.formatMode === "value" ? "value" : "classic"}
        data-test="Counter.Formatting.Mode"
        onChange={(formatMode: any) => onOptionsChange({ formatMode })}
      >
        <Select.Option value="value" data-test="Counter.Formatting.Mode.value">
          Standard: units, compact, currency
        </Select.Option>
        <Select.Option value="classic" data-test="Counter.Formatting.Mode.classic">
          Classic: decimal and thousands characters
        </Select.Option>
      </Select>
    </Section>
  );
}

export default function FormatSettings({ options, data, onOptionsChange }: any) {
  const inputsEnabled = isValueNumber(data.rows, options);
  if (options.formatMode === "value") {
    const first = (data.rows || [])[0];
    return (
      <React.Fragment>
        <FormatModeSelect options={options} onOptionsChange={onOptionsChange} />
        <ValueFormatSection
          format={options.valueFormat}
          sampleValue={first && options.counterColName ? first[options.counterColName] : undefined}
          testPrefix="Counter.Format"
          onChange={(valueFormat) => onOptionsChange({ valueFormat }, UpdateOptionsStrategy.shallowMerge)}
        />
        <Section>
          {/* @ts-expect-error ts-migrate(2745) FIXME: This JSX tag's 'children' prop expects type 'never... Remove this comment to see the full error message */}
          <Switch
            data-test="Counter.Formatting.FormatTargetValue"
            // @ts-expect-error ts-migrate(2322) FIXME: Type 'any' is not assignable to type 'never'.
            defaultChecked={options.formatTargetValue}
            // @ts-expect-error ts-migrate(2322) FIXME: Type '(formatTargetValue: any) => any' is not assi... Remove this comment to see the full error message
            onChange={(formatTargetValue: any) => onOptionsChange({ formatTargetValue })}
          >
            Format Target Value
          </Switch>
        </Section>
      </React.Fragment>
    );
  }
  return (
    <React.Fragment>
      <FormatModeSelect options={options} onOptionsChange={onOptionsChange} />
      <Section>
        <InputNumber
          layout="horizontal"
          label="Formatting Decimal Place"
          data-test="Counter.Formatting.DecimalPlace"
          defaultValue={options.stringDecimal}
          disabled={!inputsEnabled}
          onChange={(stringDecimal: any) => onOptionsChange({ stringDecimal })}
        />
      </Section>

      <Section>
        <Input
          layout="horizontal"
          label="Formatting Decimal Character"
          data-test="Counter.Formatting.DecimalCharacter"
          defaultValue={options.stringDecChar}
          disabled={!inputsEnabled}
          onChange={(e: any) => onOptionsChange({ stringDecChar: e.target.value })}
        />
      </Section>

      <Section>
        <Input
          layout="horizontal"
          label="Formatting Thousands Separator"
          data-test="Counter.Formatting.ThousandsSeparator"
          defaultValue={options.stringThouSep}
          disabled={!inputsEnabled}
          onChange={(e: any) => onOptionsChange({ stringThouSep: e.target.value })}
        />
      </Section>

      <Section>
        <Input
          layout="horizontal"
          label="Formatting String Prefix"
          data-test="Counter.Formatting.StringPrefix"
          defaultValue={options.stringPrefix}
          disabled={!inputsEnabled}
          onChange={(e: any) => onOptionsChange({ stringPrefix: e.target.value })}
        />
      </Section>

      <Section>
        <Input
          layout="horizontal"
          label="Formatting String Suffix"
          data-test="Counter.Formatting.StringSuffix"
          defaultValue={options.stringSuffix}
          disabled={!inputsEnabled}
          onChange={(e: any) => onOptionsChange({ stringSuffix: e.target.value })}
        />
      </Section>

      <Section>
        {/* @ts-expect-error ts-migrate(2745) FIXME: This JSX tag's 'children' prop expects type 'never... Remove this comment to see the full error message */}
        <Switch
          data-test="Counter.Formatting.FormatTargetValue"
          // @ts-expect-error ts-migrate(2322) FIXME: Type 'any' is not assignable to type 'never'.
          defaultChecked={options.formatTargetValue}
          // @ts-expect-error ts-migrate(2322) FIXME: Type '(formatTargetValue: any) => any' is not assi... Remove this comment to see the full error message
          onChange={(formatTargetValue: any) => onOptionsChange({ formatTargetValue })}
        >
          Format Target Value
        </Switch>
      </Section>
    </React.Fragment>
  );
}

FormatSettings.propTypes = EditorPropTypes;
