import React from "react";
import { useDebouncedCallback } from "use-debounce";
import { Section, Input, Checkbox, ContextHelp } from "@/components/visualizations/editor";
import { UpdateOptionsStrategy } from "@/components/visualizations/editor/createTabbedEditor";
import { ValueFormatSection } from "@/visualizations/shared/valueOptions/editor";
import { EditorPropTypes } from "@/visualizations/prop-types";

export default function AppearanceSettings({ options, onOptionsChange }: any) {
  const [debouncedOnOptionsChange] = useDebouncedCallback(onOptionsChange, 200);

  return (
    <React.Fragment>
      <Section>
        <Input
          layout="horizontal"
          label="Time Column Title"
          defaultValue={options.timeColumnTitle}
          onChange={(e: any) => debouncedOnOptionsChange({ timeColumnTitle: e.target.value })}
        />
      </Section>
      <Section>
        <Input
          layout="horizontal"
          label="People Column Title"
          defaultValue={options.peopleColumnTitle}
          onChange={(e: any) => debouncedOnOptionsChange({ peopleColumnTitle: e.target.value })}
        />
      </Section>
      <Section>
        <Input
          layout="horizontal"
          label={
            <React.Fragment>
              Stage Column Title
              <ContextHelp placement="topRight" arrowPointAtCenter>
                {/* @ts-expect-error ts-migrate(2322) FIXME: Type 'Element' is not assignable to type 'null | u... Remove this comment to see the full error message */}
                <div>
                  Use <code>{"{{ @ }}"}</code> to insert a stage number
                </div>
              </ContextHelp>
            </React.Fragment>
          }
          defaultValue={options.stageColumnTitle}
          onChange={(e: any) => debouncedOnOptionsChange({ stageColumnTitle: e.target.value })}
        />
      </Section>

      <ValueFormatSection
        title="Values"
        format={options.numberFormat}
        testPrefix="Cohort.NumberFormat"
        onChange={(numberFormat) => onOptionsChange({ numberFormat }, UpdateOptionsStrategy.shallowMerge)}
      />

      <ValueFormatSection
        title="Percentages"
        format={options.percentFormat}
        testPrefix="Cohort.PercentFormat"
        onChange={(percentFormat) => onOptionsChange({ percentFormat }, UpdateOptionsStrategy.shallowMerge)}
      />

      <Section>
        <Input
          layout="horizontal"
          label="No Value Placeholder"
          defaultValue={options.noValuePlaceholder}
          onChange={(e: any) => debouncedOnOptionsChange({ noValuePlaceholder: e.target.value })}
        />
      </Section>

      <Section>
        <Checkbox
          defaultChecked={options.showTooltips}
          onChange={(event) => onOptionsChange({ showTooltips: event.target.checked })}
        >
          Show Tooltips
        </Checkbox>
      </Section>
      <Section>
        <Checkbox
          defaultChecked={options.percentValues}
          onChange={(event) => onOptionsChange({ percentValues: event.target.checked })}
        >
          Normalize Values to Percentage
        </Checkbox>
      </Section>
    </React.Fragment>
  );
}

AppearanceSettings.propTypes = EditorPropTypes;
