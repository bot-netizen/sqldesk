import React from "react";
import { Section, Checkbox } from "@/components/visualizations/editor";

export default function Editor({ options, onOptionsChange }: any) {
  return (
    <React.Fragment>
      {/*
        What each stage is worth, written on the stage.

        Off by default. On a funnel eight stages wide the numbers are what
        makes it unreadable; on a narrow one they are the first thing
        anybody asks for, and reading them off the tooltip one node at a
        time is not an answer when the question is "where does it drop".
      */}
      <Section>
        <Checkbox
          data-test="Sankey.ShowNodeValues"
          checked={!!options.showNodeValues}
          onChange={(event: any) => onOptionsChange({ showNodeValues: event.target.checked })}
        >
          Show each stage's value
        </Checkbox>
      </Section>
      <p>This visualization expects the query result to have rows in the following format:</p>
      <ul>
        <li>
          <strong>stage1</strong> - stage 1 value
        </li>
        <li>
          <strong>stage2</strong> - stage 2 value (or null)
        </li>
        <li>
          <strong>stage3</strong> … <strong>stageN</strong> - as many further stages as the funnel has (or null)
        </li>
        <li>
          <strong>value</strong> - number of times this sequence occurred
        </li>
      </ul>
    </React.Fragment>
  );
}
