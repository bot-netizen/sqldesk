import React from "react";
import createTabbedEditor, { UpdateOptionsStrategy } from "@/components/visualizations/editor/createTabbedEditor";
import { Section, Select, InputNumber, Checkbox, ControlLabel } from "@/components/visualizations/editor";
import { ValueFormatSection, ColorSelect } from "../shared/valueOptions/editor";
import { ColumnSelect } from "../shared/editorControls";
import { numericColumns } from "../shared/rows";
import { MAX_BINS, suggestBinCount, readValues } from "./binning";

function GeneralSettings({ options, data, onOptionsChange }: any) {
  const columns = data.columns || [];
  // Only numeric columns can be binned, but a column already chosen stays on
  // the list even if this result's sample does not look numeric.
  const numeric = numericColumns(columns, data.rows || []);
  const choices = numeric.some((c: any) => c.name === options.valueColumn)
    ? numeric
    : columns.filter((c: any) => c.name === options.valueColumn).concat(numeric);

  const { values } = readValues(data.rows || [], options.valueColumn);
  const suggested = values.length ? suggestBinCount(values) : 1;

  return (
    <React.Fragment>
      <Section>
        <ColumnSelect
          label="Column to bin"
          value={options.valueColumn}
          columns={choices}
          onChange={(valueColumn) => onOptionsChange({ valueColumn })}
          data-test="Histogram.ValueColumn"
        />
      </Section>

      <Section>
        <ControlLabel label="Bins">
          <Checkbox
            checked={options.binCount === null}
            data-test="Histogram.AutoBins"
            onChange={(event: any) =>
              onOptionsChange({ binCount: event.target.checked ? null : suggested }, UpdateOptionsStrategy.shallowMerge)
            }
          >
            Choose from the data{options.binCount === null && values.length ? ` (${suggested} now)` : ""}
          </Checkbox>
        </ControlLabel>
      </Section>

      {options.binCount !== null && (
        <Section>
          <InputNumber
            layout="horizontal"
            label="Number of bins"
            min={1}
            max={MAX_BINS}
            value={options.binCount}
            data-test="Histogram.BinCount"
            onChange={(binCount: any) =>
              onOptionsChange({ binCount: Number(binCount) || 1 }, UpdateOptionsStrategy.shallowMerge)
            }
          />
        </Section>
      )}

      <Section>
        <Select
          layout="horizontal"
          label="Bars show"
          value={options.countMode}
          data-test="Histogram.CountMode"
          onChange={(countMode: any) => onOptionsChange({ countMode })}
        >
          <Select.Option value="count" data-test="Histogram.CountMode.count">
            How many rows
          </Select.Option>
          <Select.Option value="percent" data-test="Histogram.CountMode.percent">
            Share of all rows
          </Select.Option>
        </Select>
      </Section>

      <Section>
        <ControlLabel label="Bar colour">
          <ColorSelect
            value={options.color}
            data-test="Histogram.Color"
            aria-label="Bar colour"
            onChange={(color) => onOptionsChange({ color }, UpdateOptionsStrategy.shallowMerge)}
          />
        </ControlLabel>
      </Section>

      <Section>
        <Checkbox
          checked={options.showMean}
          data-test="Histogram.ShowMean"
          onChange={(event: any) =>
            onOptionsChange({ showMean: event.target.checked }, UpdateOptionsStrategy.shallowMerge)
          }
        >
          Draw the mean
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
      testPrefix="Histogram.Format"
      onChange={(valueFormat) => onOptionsChange({ valueFormat }, UpdateOptionsStrategy.shallowMerge)}
    />
  );
}

export default createTabbedEditor([
  { key: "General", title: "General", component: GeneralSettings },
  { key: "Format", title: "Format", component: FormatSettings },
]);
