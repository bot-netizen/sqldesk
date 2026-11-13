import { map } from "lodash";
import React, { useMemo, useRef } from "react";
import { UpdateOptionsStrategy } from "@/components/visualizations/editor/createTabbedEditor";
import Button from "antd/lib/button";
import { Section, Select, TextArea } from "@/components/visualizations/editor";
import { AGGREGATES, FILTERS, render } from "../template";

/*
  Write the sentence; drop values into it.

  The template is plain words with {{ ... }} where a value goes. The buttons
  under it insert a column where the cursor is, so nobody has to remember a
  column's exact name -- and anything the template asks for that the result
  cannot answer is listed under it as it is typed, in the words the summary
  itself would show.
*/

const LAYOUT_LABELS: Record<string, string> = {
  sentence: "Sentence",
  bullets: "Bullets, one per line",
  status: "Status line",
};

export default function TextSettings({ options, data, onOptionsChange }: any) {
  // Where the cursor was last, for inserting there. Read off the text area's
  // own events: the editor's text area does not pass a ref through.
  const cursor = useRef<number | null>(null);
  const remember = (event: any) => {
    cursor.current = typeof event.target.selectionStart === "number" ? event.target.selectionStart : null;
  };
  const columns = (data && data.columns) || [];

  const problems = useMemo(
    () => render(options.template || "", data || {}, options.rules || []).filter((piece) => piece.kind === "problem"),
    [options.template, options.rules, data]
  );

  const insert = (text: string) => {
    const template = options.template || "";
    const at = cursor.current === null ? template.length : Math.min(cursor.current, template.length);
    cursor.current = at + text.length;
    onOptionsChange(
      { template: template.slice(0, at) + text + template.slice(at) },
      UpdateOptionsStrategy.shallowMerge
    );
  };

  return (
    <React.Fragment>
      <Section>
        <Select
          layout="horizontal"
          label="Layout"
          data-test="Summary.Layout"
          value={options.layout}
          onChange={(layout: any) => onOptionsChange({ layout }, UpdateOptionsStrategy.shallowMerge)}
        >
          {map(LAYOUT_LABELS, (label, value) => (
            <Select.Option key={value} value={value} data-test={`Summary.Layout.${value}`}>
              {label}
            </Select.Option>
          ))}
        </Select>
      </Section>

      <Section>
        <TextArea
          label="Text"
          data-test="Summary.Template"
          rows={6}
          value={options.template}
          placeholder="Revenue this week is {{ sum(revenue) | currency }}."
          onChange={(event: any) => {
            remember(event);
            onOptionsChange({ template: event.target.value }, UpdateOptionsStrategy.shallowMerge);
          }}
          onSelect={remember}
          onClick={remember}
          onKeyUp={remember}
        />
      </Section>

      {problems.length > 0 && (
        <Section>
          <div className="summary-editor-problems" data-test="Summary.Problems">
            {problems.map((problem, index) => (
              // eslint-disable-next-line react/no-array-index-key
              <div key={index}>
                <code>{problem.kind === "problem" ? problem.expression : ""}</code>{" "}
                {problem.kind === "problem" ? problem.text : ""}
              </div>
            ))}
          </div>
        </Section>
      )}

      <Section>
        <div className="summary-editor-label">Insert a column</div>
        <div className="summary-editor-chips" data-test="Summary.Columns">
          {columns.map((column: any) => (
            <Button
              key={column.name}
              size="small"
              data-test={`Summary.Insert.${column.name}`}
              onClick={() => insert(`{{ ${column.name} }}`)}
            >
              {column.name}
            </Button>
          ))}
          <Button size="small" data-test="Summary.Insert.count" onClick={() => insert("{{ count() }}")}>
            row count
          </Button>
        </div>
      </Section>

      <Section>
        <div className="summary-editor-help" data-test="Summary.Help">
          <div>
            <code>{"{{ revenue }}"}</code> the first row&rsquo;s value
          </div>
          <div>
            <code>{"{{ sum(revenue) }}"}</code> over every row &mdash; {AGGREGATES.join(", ")}
          </div>
          <div>
            <code>{'{{ revenue where region = "West" }}'}</code> one row by another column
          </div>
          <div>
            <code>{"{{ change | percent | arrow }}"}</code> formatted &mdash; {FILTERS.join(", ")}
          </div>
        </div>
      </Section>
    </React.Fragment>
  );
}
