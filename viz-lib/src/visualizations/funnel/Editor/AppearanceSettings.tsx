import React from "react";
import { useDebouncedCallback } from "use-debounce";
import { Section, InputNumber } from "@/components/visualizations/editor";
import { UpdateOptionsStrategy } from "@/components/visualizations/editor/createTabbedEditor";
import { ValueFormatSection } from "@/visualizations/shared/valueOptions/editor";
import { EditorPropTypes } from "@/visualizations/prop-types";

export default function AppearanceSettings({ options, onOptionsChange }: any) {
  const [onOptionsChangeDebounced] = useDebouncedCallback(onOptionsChange, 200);

  return (
    <React.Fragment>
      <ValueFormatSection
        title="Values"
        format={options.numberFormat}
        testPrefix="Funnel.NumberFormat"
        onChange={(numberFormat) => onOptionsChange({ numberFormat }, UpdateOptionsStrategy.shallowMerge)}
      />

      <ValueFormatSection
        title="Percentages"
        format={options.percentFormat}
        testPrefix="Funnel.PercentFormat"
        onChange={(percentFormat) => onOptionsChange({ percentFormat }, UpdateOptionsStrategy.shallowMerge)}
      />

      <Section>
        <InputNumber
          layout="horizontal"
          label="Items Count Limit"
          data-test="Funnel.ItemsLimit"
          min={2}
          defaultValue={options.itemsLimit}
          onChange={(itemsLimit: any) => onOptionsChangeDebounced({ itemsLimit })}
        />
      </Section>

      <Section>
        <InputNumber
          layout="horizontal"
          label="Min Percent Value"
          data-test="Funnel.PercentRangeMin"
          min={0}
          defaultValue={options.percentValuesRange.min}
          onChange={(min: any) => onOptionsChangeDebounced({ percentValuesRange: { min } })}
        />
      </Section>

      <Section>
        <InputNumber
          layout="horizontal"
          label="Max Percent Value"
          data-test="Funnel.PercentRangeMax"
          min={0}
          defaultValue={options.percentValuesRange.max}
          onChange={(max: any) => onOptionsChangeDebounced({ percentValuesRange: { max } })}
        />
      </Section>
    </React.Fragment>
  );
}

AppearanceSettings.propTypes = EditorPropTypes;
