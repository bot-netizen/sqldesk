import React from "react";
import { UpdateOptionsStrategy } from "@/components/visualizations/editor/createTabbedEditor";
import { Section, Select, InputNumber, Switch } from "@/components/visualizations/editor";
import { ColumnSelect } from "../../shared/editorControls";
import { DEFAULT_SPARKLINE, DEFAULT_COMPARISON } from "../stat";

// The editor kit's Switch declares its props as `never`; one cast here beats
// an expect-error on every prop.
const SwitchControl = Switch as any;

export default function TrendSettings({ options, data, onOptionsChange }: any) {
  const spark = { ...DEFAULT_SPARKLINE, ...(options.sparkline || {}) };
  const comparison = { ...DEFAULT_COMPARISON, ...(options.comparison || {}) };
  const setSpark = (changes: any) =>
    onOptionsChange({ sparkline: { ...spark, ...changes } }, UpdateOptionsStrategy.shallowMerge);
  const setComparison = (changes: any) =>
    onOptionsChange({ comparison: { ...comparison, ...changes } }, UpdateOptionsStrategy.shallowMerge);

  return (
    <React.Fragment>
      {/* @ts-expect-error Section's children type is too narrow in its declaration */}
      <Section>
        <SwitchControl
          data-test="Counter.Trend.Sparkline"
          checked={spark.enabled}
          disabled={options.countRow}
          onChange={(enabled: boolean) => setSpark({ enabled })}
        >
          Show a sparkline
        </SwitchControl>
        {spark.enabled && (
          <p className="value-options-help">
            Draws the value column across all rows. The latest row becomes the headline number.
          </p>
        )}
      </Section>

      {spark.enabled && (
        // @ts-expect-error Section's children type is too narrow in its declaration
        <Section>
          <ColumnSelect
            label="Time column"
            value={spark.timeColumn}
            columns={data.columns || []}
            noneLabel="Keep the query's order"
            onChange={(timeColumn) => setSpark({ timeColumn })}
            data-test="Counter.Trend.TimeColumn"
          />
        </Section>
      )}

      {/* @ts-expect-error Section's children type is too narrow in its declaration */}
      <Section>
        <Select
          layout="horizontal"
          label="Compare with"
          value={comparison.mode}
          data-test="Counter.Trend.Compare"
          onChange={(mode: any) => setComparison({ mode })}
        >
          {/* @ts-expect-error Select.Option is added by withControlLabel's wrapped component */}
          <Select.Option value="none" data-test="Counter.Trend.Compare.none">
            Nothing
            {/* @ts-expect-error see above */}
          </Select.Option>
          {/* @ts-expect-error see above */}
          <Select.Option value="previous" data-test="Counter.Trend.Compare.previous">
            The previous row
            {/* @ts-expect-error see above */}
          </Select.Option>
          {/* @ts-expect-error see above */}
          <Select.Option value="rowsBack" data-test="Counter.Trend.Compare.rowsBack">
            A number of rows back
            {/* @ts-expect-error see above */}
          </Select.Option>
          {/* @ts-expect-error see above */}
          <Select.Option value="target" data-test="Counter.Trend.Compare.target">
            The target value
            {/* @ts-expect-error see above */}
          </Select.Option>
          {/* @ts-expect-error see above */}
          <Select.Option value="previousRefresh" data-test="Counter.Trend.Compare.previousRefresh">
            The last refresh
            {/* @ts-expect-error see above */}
          </Select.Option>
        </Select>
        {comparison.mode === "target" && !options.targetColName && (
          <p className="value-options-help">Choose a target value column on the General tab.</p>
        )}
        {comparison.mode === "previousRefresh" && (
          <p className="value-options-help">Shows once the value has refreshed at least once while on screen.</p>
        )}
      </Section>

      {comparison.mode === "rowsBack" && (
        // @ts-expect-error Section's children type is too narrow in its declaration
        <Section>
          <InputNumber
            layout="horizontal"
            label="Rows back"
            min={1}
            value={comparison.rowsBack}
            data-test="Counter.Trend.RowsBack"
            onChange={(rowsBack: any) => setComparison({ rowsBack: Math.max(1, Math.round(Number(rowsBack) || 1)) })}
          />
        </Section>
      )}

      {comparison.mode !== "none" && (
        <React.Fragment>
          {/* @ts-expect-error Section's children type is too narrow in its declaration */}
          <Section>
            <Select
              layout="horizontal"
              label="Show change as"
              value={comparison.display}
              data-test="Counter.Trend.Display"
              onChange={(display: any) => setComparison({ display })}
            >
              {/* @ts-expect-error Select.Option is added by withControlLabel's wrapped component */}
              <Select.Option value="percent">Percent</Select.Option>
              {/* @ts-expect-error see above */}
              <Select.Option value="absolute">Difference</Select.Option>
            </Select>
          </Section>
          {/* @ts-expect-error Section's children type is too narrow in its declaration */}
          <Section>
            <Select
              layout="horizontal"
              label="A rise is"
              value={comparison.upIsGood ? "good" : "bad"}
              data-test="Counter.Trend.UpIsGood"
              onChange={(v: any) => setComparison({ upIsGood: v === "good" })}
            >
              {/* @ts-expect-error Select.Option is added by withControlLabel's wrapped component */}
              <Select.Option value="good">Good (revenue, sign-ups)</Select.Option>
              {/* @ts-expect-error see above */}
              <Select.Option value="bad">Bad (errors, latency)</Select.Option>
            </Select>
          </Section>
        </React.Fragment>
      )}
    </React.Fragment>
  );
}
