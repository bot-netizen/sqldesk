import React from "react";
import createTabbedEditor, { UpdateOptionsStrategy } from "@/components/visualizations/editor/createTabbedEditor";
import { Section, Input, Checkbox, ControlLabel } from "@/components/visualizations/editor";
import { ValueMappingsSection, ColorSelect } from "../shared/valueOptions/editor";
import { ColumnSelect } from "../shared/editorControls";

function GeneralSettings({ options, data, onOptionsChange }: any) {
  const columns = data.columns || [];
  return (
    <React.Fragment>
      <Section>
        <ColumnSelect
          label="Track column"
          value={options.laneColumn}
          columns={columns}
          noneLabel="One track for everything"
          onChange={(laneColumn) => onOptionsChange({ laneColumn })}
          data-test="Timeline.LaneColumn"
        />
      </Section>

      <Section>
        <ColumnSelect
          label="Start column"
          value={options.startColumn}
          columns={columns}
          onChange={(startColumn) => onOptionsChange({ startColumn })}
          data-test="Timeline.StartColumn"
        />
      </Section>

      <Section>
        <ColumnSelect
          label="End column"
          value={options.endColumn}
          columns={columns}
          noneLabel="Use a duration instead"
          onChange={(endColumn) => onOptionsChange({ endColumn })}
          data-test="Timeline.EndColumn"
        />
      </Section>

      {!options.endColumn && (
        <Section>
          <ColumnSelect
            label="Duration, in seconds"
            value={options.durationColumn}
            columns={columns}
            noneLabel="Still running"
            onChange={(durationColumn) => onOptionsChange({ durationColumn })}
            data-test="Timeline.DurationColumn"
          />
        </Section>
      )}

      <Section>
        <ColumnSelect
          label="State column"
          value={options.stateColumn}
          columns={columns}
          noneLabel="One colour for everything"
          onChange={(stateColumn) => onOptionsChange({ stateColumn })}
          data-test="Timeline.StateColumn"
        />
      </Section>

      {!options.stateColumn && (
        <Section>
          <ControlLabel label="Bar colour">
            <ColorSelect
              value={options.defaultColor}
              data-test="Timeline.DefaultColor"
              aria-label="Bar colour"
              onChange={(defaultColor) => onOptionsChange({ defaultColor }, UpdateOptionsStrategy.shallowMerge)}
            />
          </ControlLabel>
        </Section>
      )}

      <Section>
        <Checkbox
          checked={options.showLabels}
          data-test="Timeline.ShowLabels"
          onChange={(event: any) =>
            onOptionsChange({ showLabels: event.target.checked }, UpdateOptionsStrategy.shallowMerge)
          }
        >
          Write the state on each bar
        </Checkbox>
      </Section>

      <Section>
        <Input
          layout="horizontal"
          label="Time format"
          value={options.timeFormat}
          data-test="Timeline.TimeFormat"
          onChange={(event: any) =>
            onOptionsChange({ timeFormat: event.target.value }, UpdateOptionsStrategy.shallowMerge)
          }
        />
      </Section>
    </React.Fragment>
  );
}

function StateSettings({ options, onOptionsChange }: any) {
  return (
    <ValueMappingsSection
      mappings={options.mappings}
      testPrefix="Timeline"
      description="Each state's colour and, if you want one, a friendlier name for it. States with no mapping take the next colour from the palette."
      onChange={(mappings) => onOptionsChange({ mappings }, UpdateOptionsStrategy.shallowMerge)}
    />
  );
}

export default createTabbedEditor([
  { key: "General", title: "General", component: GeneralSettings },
  { key: "States", title: "States", component: StateSettings },
]);
