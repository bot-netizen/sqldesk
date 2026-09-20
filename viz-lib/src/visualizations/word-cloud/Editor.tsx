import { map, merge } from "lodash";
import React from "react";
import * as Grid from "antd/lib/grid";
import { Section, Select, InputNumber, ControlLabel } from "@/components/visualizations/editor";
import { EditorPropTypes } from "@/visualizations/prop-types";

export default function Editor({ options, data, onOptionsChange }: any) {
  const optionsChanged = (newOptions: any) => {
    onOptionsChange(merge({}, options, newOptions));
  };

  return (
    <React.Fragment>
      <Section>
        <Select
          label="Words Column"
          data-test="WordCloud.WordsColumn"
          value={options.column}
          onChange={(column: any) => optionsChanged({ column })}
        >
          {map(data.columns, ({ name }) => (
            <Select.Option key={name} data-test={"WordCloud.WordsColumn." + name}>
              {name}
            </Select.Option>
          ))}
        </Select>
      </Section>
      <Section>
        <Select
          label="Frequencies Column"
          data-test="WordCloud.FrequenciesColumn"
          value={options.frequenciesColumn}
          onChange={(frequenciesColumn: any) => optionsChanged({ frequenciesColumn })}
        >
          <Select.Option key="none" value="">
            <i>(count word frequencies automatically)</i>
          </Select.Option>
          {map(data.columns, ({ name }) => (
            <Select.Option key={"column-" + name} value={name} data-test={"WordCloud.FrequenciesColumn." + name}>
              {name}
            </Select.Option>
          ))}
        </Select>
      </Section>
      <Section>
        <ControlLabel label="Words Length Limit">
          {/* @ts-expect-error antd 4 dropped Row's `type` prop but still honours it */}
          <Grid.Row gutter={15} type="flex">
            <Grid.Col span={12}>
              <InputNumber
                data-test="WordCloud.WordLengthLimit.Min"
                placeholder="Min"
                min={0}
                value={options.wordLengthLimit.min}
                onChange={(value: any) => optionsChanged({ wordLengthLimit: { min: value > 0 ? value : null } })}
              />
            </Grid.Col>
            <Grid.Col span={12}>
              <InputNumber
                data-test="WordCloud.WordLengthLimit.Max"
                placeholder="Max"
                min={0}
                value={options.wordLengthLimit.max}
                onChange={(value: any) => optionsChanged({ wordLengthLimit: { max: value > 0 ? value : null } })}
              />
            </Grid.Col>
          </Grid.Row>
        </ControlLabel>
      </Section>
      <Section>
        <ControlLabel label="Frequencies Limit">
          {/* @ts-expect-error antd 4 dropped Row's `type` prop but still honours it */}
          <Grid.Row gutter={15} type="flex">
            <Grid.Col span={12}>
              <InputNumber
                data-test="WordCloud.WordCountLimit.Min"
                placeholder="Min"
                min={0}
                value={options.wordCountLimit.min}
                onChange={(value: any) => optionsChanged({ wordCountLimit: { min: value > 0 ? value : null } })}
              />
            </Grid.Col>
            <Grid.Col span={12}>
              <InputNumber
                data-test="WordCloud.WordCountLimit.Max"
                placeholder="Max"
                min={0}
                value={options.wordCountLimit.max}
                onChange={(value: any) => optionsChanged({ wordCountLimit: { max: value > 0 ? value : null } })}
              />
            </Grid.Col>
          </Grid.Row>
        </ControlLabel>
      </Section>
    </React.Fragment>
  );
}

Editor.propTypes = EditorPropTypes;
