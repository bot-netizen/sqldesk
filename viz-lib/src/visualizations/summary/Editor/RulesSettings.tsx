import React from "react";
import Button from "antd/lib/button";
import Input from "antd/lib/input";
import Select from "antd/lib/select";
import { Section } from "@/components/visualizations/editor";
import { UpdateOptionsStrategy } from "@/components/visualizations/editor/createTabbedEditor";
import { Rule } from "../template";

/*
  Colour a value by what it is.

  One line per rule: a column, a test, and what a value that passes looks
  like -- good, bad, watch -- with an arrow or a mark if wanted. The first
  rule that holds for a value wins, so a list reads top to bottom the way
  somebody would explain it: "below zero is bad; otherwise good".
*/

const OPERATORS = [
  { value: ">", label: "above" },
  { value: ">=", label: "at least" },
  { value: "<", label: "below" },
  { value: "<=", label: "at most" },
  { value: "between", label: "between" },
  { value: "=", label: "is" },
  { value: "!=", label: "is not" },
];
const TONES = [
  { value: "good", label: "Good" },
  { value: "bad", label: "Bad" },
  { value: "watch", label: "Watch" },
  { value: "neutral", label: "Neutral" },
];
const ICONS = [
  { value: "none", label: "No mark" },
  { value: "up", label: "▲ up" },
  { value: "down", label: "▼ down" },
  { value: "check", label: "✓ check" },
  { value: "alert", label: "⚠ alert" },
];

export default function RulesSettings({ options, data, onOptionsChange }: any) {
  const rules: Rule[] = options.rules || [];
  const columns = [...((data && data.columns) || []).map((column: any) => column.name), "count"];

  // Replaced whole, not merged: the editor's default deep merge would put a
  // removed rule straight back, because merging a shorter list into a longer
  // one keeps the longer one's tail.
  const save = (next: Rule[]) => onOptionsChange({ rules: next }, UpdateOptionsStrategy.shallowMerge);
  const update = (index: number, change: Partial<Rule>) =>
    save(rules.map((rule, at) => (at === index ? { ...rule, ...change } : rule)));
  const remove = (index: number) => save(rules.filter((_rule, at) => at !== index));
  const add = () =>
    save([...rules, { column: columns[0] || "count", op: ">=", value: "0", tone: "good", icon: "none" }]);

  return (
    <React.Fragment>
      <Section>
        <div className="summary-editor-help">
          The first rule that holds for a value colours it. A value no rule matches is left plain.
        </div>
      </Section>
      {rules.map((rule, index) => (
        // eslint-disable-next-line react/no-array-index-key
        <Section key={index}>
          <div className="summary-editor-rule" data-test={`Summary.Rule.${index}`}>
            <div className="summary-editor-rule-line">
              <span className="summary-editor-rule-word">When</span>
              <Select
                size="small"
                value={rule.column}
                style={{ width: 120 }}
                data-test={`Summary.Rule.${index}.Column`}
                onChange={(column: any) => update(index, { column })}
                options={columns.map((name: string) => ({ value: name, label: name }))}
              />
              <Select
                size="small"
                value={rule.op}
                style={{ width: 90 }}
                data-test={`Summary.Rule.${index}.Op`}
                onChange={(op: any) => update(index, { op })}
                options={OPERATORS}
              />
              <Input
                size="small"
                value={rule.value}
                style={{ width: 80 }}
                data-test={`Summary.Rule.${index}.Value`}
                onChange={(event: any) => update(index, { value: event.target.value })}
              />
              {rule.op === "between" && (
                <Input
                  size="small"
                  value={rule.value2}
                  style={{ width: 80 }}
                  data-test={`Summary.Rule.${index}.Value2`}
                  onChange={(event: any) => update(index, { value2: event.target.value })}
                />
              )}
            </div>
            <div className="summary-editor-rule-line">
              <span className="summary-editor-rule-word">show as</span>
              <Select
                size="small"
                value={rule.tone}
                style={{ width: 90 }}
                data-test={`Summary.Rule.${index}.Tone`}
                onChange={(tone: any) => update(index, { tone })}
                options={TONES}
              />
              <Select
                size="small"
                value={rule.icon || "none"}
                style={{ width: 100 }}
                data-test={`Summary.Rule.${index}.Icon`}
                onChange={(icon: any) => update(index, { icon })}
                options={ICONS}
              />
              <Button size="small" type="link" data-test={`Summary.Rule.${index}.Remove`} onClick={() => remove(index)}>
                Remove
              </Button>
            </div>
          </div>
        </Section>
      ))}
      <Section>
        <Button data-test="Summary.Rule.Add" onClick={add}>
          Add a rule
        </Button>
      </Section>
    </React.Fragment>
  );
}
