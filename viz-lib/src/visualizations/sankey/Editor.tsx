import React, { useMemo } from "react";
import { uniq } from "lodash";
import ColorPickerComponent from "@/components/ColorPicker";
import { Section, Checkbox, Select } from "@/components/visualizations/editor";
import { AllColorPalettes } from "@/visualizations/ColorPalette";
import {
  CLASSIC,
  NEUTRAL_NODE,
  SANKEY_PALETTES,
  SANKEY_SCHEMES,
  buildGraph,
  prepareDataRows,
  problemWith,
  LinkColor,
  NodeAlign,
  NodePercent,
  WidthScale,
} from "./buildOption";
import "./editor.less";

const FLOW_COLOURS: { value: LinkColor; label: string }[] = [
  { value: "gradient", label: "Fade from one stage's colour to the next" },
  { value: "source", label: "One colour, the stage it leaves" },
  { value: "journey", label: "Each journey keeps its first stage's colour" },
  { value: "target", label: "One colour, the stage it reaches (colour your outcomes)" },
  { value: "continues", label: "One colour for what continues, grey where it stops" },
];

const ALIGNS: { value: NodeAlign; label: string }[] = [
  { value: "justify", label: "Last stages at the right edge" },
  { value: "left", label: "Each stage in its own column, from the left" },
];

const PERCENTS: { value: NodePercent; label: string }[] = [
  { value: "none", label: "None" },
  { value: "total", label: "Of the total" },
  { value: "previous", label: "Of the stage before" },
];

const WIDTHS: { value: WidthScale; label: string }[] = [
  { value: "linear", label: "To scale" },
  { value: "sqrt", label: "Compressed, so small flows show" },
];

// Its declared props come out as `never` (the chart editor works round the
// same thing line by line); typed loosely once here instead.
const ColorPicker: any = ColorPickerComponent;

/** Labels can be chosen for colours and for leaving out; a ceiling on the list. */
const MAX_LABELS = 60;

export default function Editor({ options, data, onOptionsChange }: any) {
  // The dialog takes what the editor gives as the whole of the options, so
  // every change carries the rest with it.
  const set = (changes: any) => onOptionsChange({ ...options, ...changes });

  const graph = useMemo(() => {
    if (!data || problemWith({ ...data, rows: prepareDataRows(data.rows || []) })) {
      return null;
    }
    return buildGraph(prepareDataRows(data.rows), {
      colorScheme: options.colorScheme,
      linkColor: options.linkColor,
      nodeColors: options.nodeColors,
    });
  }, [data, options.colorScheme, options.linkColor, options.nodeColors]);

  const labels = useMemo(
    () => (graph ? uniq(graph.nodes.map((node) => node.displayName)).slice(0, MAX_LABELS) : []),
    [graph]
  );

  // The labels a colour can be chosen for: in journey mode only the first
  // stage's mean anything, since every later stage is drawn neutral.
  const colourable = useMemo(() => {
    if (!graph) {
      return [];
    }
    const nodes = options.linkColor === "journey" ? graph.nodes.filter((node) => node.depth === 0) : graph.nodes;
    const seen = new Map<string, string>();
    nodes.forEach((node) => {
      if (!seen.has(node.displayName) && seen.size < MAX_LABELS) {
        seen.set(node.displayName, node.itemStyle.color);
      }
    });
    return Array.from(seen.entries());
  }, [graph, options.linkColor]);

  // The palette's own colours to pick from, and a grey: greying a label out
  // is how a stage stops drawing the eye ("continues" greys flows into it).
  const presets = useMemo(() => {
    const scheme = options.colorScheme;
    const chartPalette = scheme && scheme !== CLASSIC ? (AllColorPalettes as any)[scheme] : null;
    const own: string[] =
      SANKEY_PALETTES[scheme] ||
      (chartPalette ? (Object.values(chartPalette) as string[]) : [...SANKEY_PALETTES.Calm, ...SANKEY_PALETTES.Soft]);
    return uniq([...own, NEUTRAL_NODE]);
  }, [options.colorScheme]);

  return (
    <React.Fragment>
      <Section>
        <Select
          label="Colours"
          data-test="Sankey.ColorScheme"
          value={options.colorScheme || CLASSIC}
          onChange={(colorScheme: any) => set({ colorScheme, nodeColors: {} })}
        >
          {SANKEY_SCHEMES.map((scheme) => (
            <Select.Option key={scheme} value={scheme}>
              {scheme === CLASSIC ? "Classic (as before)" : scheme}
            </Select.Option>
          ))}
        </Select>
      </Section>

      <Section>
        <Select
          label="Flows"
          data-test="Sankey.LinkColor"
          value={options.linkColor || "gradient"}
          onChange={(linkColor: any) => set({ linkColor })}
        >
          {FLOW_COLOURS.map((item) => (
            <Select.Option key={item.value} value={item.value}>
              {item.label}
            </Select.Option>
          ))}
        </Select>
      </Section>

      {colourable.length > 0 && (
        <Section>
          <div className="sankey-editor-colours" data-test="Sankey.NodeColors">
            {colourable.map(([label, color]) => (
              <div className="sankey-editor-colour" key={label}>
                <ColorPicker
                  interactive
                  presetColors={presets}
                  placement="topLeft"
                  color={color}
                  onChange={(value: any) => set({ nodeColors: { ...(options.nodeColors || {}), [label]: value } })}
                  addonAfter={<ColorPicker.Label color={color} presetColors={presets} />}
                />
                <span className="sankey-editor-colour-label">{label}</span>
              </div>
            ))}
          </div>
        </Section>
      )}

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
          onChange={(event: any) => set({ showNodeValues: event.target.checked })}
        >
          Show each stage's value
        </Checkbox>
      </Section>

      <Section>
        <Select
          label="Percentages on each stage"
          data-test="Sankey.NodePercent"
          value={options.nodePercent || "none"}
          onChange={(nodePercent: any) => set({ nodePercent })}
        >
          {PERCENTS.map((item) => (
            <Select.Option key={item.value} value={item.value}>
              {item.label}
            </Select.Option>
          ))}
        </Select>
      </Section>

      <Section>
        <Checkbox
          data-test="Sankey.FlowLabels"
          checked={!!options.flowLabels}
          onChange={(event: any) => set({ flowLabels: event.target.checked })}
        >
          Label each flow with its share of the stage it leaves
        </Checkbox>
      </Section>

      {/* When one flow is most of the total, everything else is a hairline. */}
      <Section>
        <Select
          label="Leave out"
          mode="multiple"
          allowClear
          placeholder="Draw every stage"
          data-test="Sankey.HiddenNodes"
          value={options.hiddenNodes || []}
          onChange={(hiddenNodes: any) => set({ hiddenNodes })}
        >
          {labels.map((label) => (
            <Select.Option key={label} value={label}>
              {label}
            </Select.Option>
          ))}
        </Select>
      </Section>

      <Section>
        <Select
          label="Stages"
          data-test="Sankey.NodeAlign"
          value={options.nodeAlign || "justify"}
          onChange={(nodeAlign: any) => set({ nodeAlign })}
        >
          {ALIGNS.map((item) => (
            <Select.Option key={item.value} value={item.value}>
              {item.label}
            </Select.Option>
          ))}
        </Select>
      </Section>

      <Section>
        <Select
          label="Flow widths"
          data-test="Sankey.WidthScale"
          value={options.widthScale || "linear"}
          onChange={(widthScale: any) => set({ widthScale })}
        >
          {WIDTHS.map((item) => (
            <Select.Option key={item.value} value={item.value}>
              {item.label}
            </Select.Option>
          ))}
        </Select>
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
      <p>Percentages are worked out from the flows, so the query needs no column for them.</p>
    </React.Fragment>
  );
}
