import { includes } from "lodash";
import React from "react";
import { useDebouncedCallback } from "use-debounce";
import { Section, Input, Checkbox, ContextHelp } from "@/components/visualizations/editor";
import { UpdateOptionsStrategy } from "@/components/visualizations/editor/createTabbedEditor";
import { ValueFormatSection } from "@/visualizations/shared/valueOptions/editor";
import { EditorPropTypes } from "@/visualizations/prop-types";

export default function DataLabelsSettings({ options, onOptionsChange }: any) {
  const isShowDataLabelsAvailable = includes(
    ["line", "area", "column", "scatter", "pie", "heatmap"],
    options.globalSeriesType
  );

  const [debouncedOnOptionsChange] = useDebouncedCallback(onOptionsChange, 200);

  return (
    <React.Fragment>
      {isShowDataLabelsAvailable && (
        <Section>
          <Checkbox
            data-test="Chart.DataLabels.ShowDataLabels"
            defaultChecked={options.showDataLabels}
            onChange={(event) => onOptionsChange({ showDataLabels: event.target.checked })}
          >
            Show Data Labels
          </Checkbox>
        </Section>
      )}

      <ValueFormatSection
        title="Values"
        format={options.numberFormat}
        testPrefix="Chart.DataLabels.NumberFormat"
        onChange={(numberFormat) => onOptionsChange({ numberFormat }, UpdateOptionsStrategy.shallowMerge)}
      />

      <ValueFormatSection
        title="Percentages"
        format={options.percentFormat}
        testPrefix="Chart.DataLabels.PercentFormat"
        onChange={(percentFormat) => onOptionsChange({ percentFormat }, UpdateOptionsStrategy.shallowMerge)}
      />

      <Section>
        <Input
          label={
            <React.Fragment>
              Date/Time Values Format
              <ContextHelp.DateTimeFormatSpecs />
            </React.Fragment>
          }
          data-test="Chart.DataLabels.DateTimeFormat"
          defaultValue={options.dateTimeFormat}
          onChange={(e: any) => debouncedOnOptionsChange({ dateTimeFormat: e.target.value })}
        />
      </Section>

      <Section>
        <Input
          label={
            <React.Fragment>
              Data Labels
              {/* @ts-expect-error ts-migrate(2746) FIXME: This JSX tag's 'children' prop expects a single ch... Remove this comment to see the full error message */}
              <ContextHelp placement="topRight" arrowPointAtCenter>
                <div style={{ paddingBottom: 5 }}>Use special names to access additional properties:</div>
                <div>
                  <code>{"{{ @@name }}"}</code> series name;
                </div>
                <div>
                  <code>{"{{ @@x }}"}</code> x-value;
                </div>
                <div>
                  <code>{"{{ @@y }}"}</code> y-value;
                </div>
                <div>
                  <code>{"{{ @@yPercent }}"}</code> relative y-value;
                </div>
                <div>
                  <code>{"{{ @@yError }}"}</code> y deviation;
                </div>
                <div>
                  <code>{"{{ @@size }}"}</code> bubble size;
                </div>
                <div style={{ paddingTop: 5 }}>
                  Also, all query result columns can be referenced
                  <br />
                  using
                  <code style={{ whiteSpace: "nowrap" }}>{"{{ column_name }}"}</code> syntax.
                </div>
              </ContextHelp>
            </React.Fragment>
          }
          data-test="Chart.DataLabels.TextFormat"
          placeholder="(auto)"
          defaultValue={options.textFormat}
          onChange={(e: any) => debouncedOnOptionsChange({ textFormat: e.target.value })}
        />
      </Section>
    </React.Fragment>
  );
}

DataLabelsSettings.propTypes = EditorPropTypes;
