import { keys } from "lodash";
import React from "react";
import Button from "antd/lib/button";
import AntInput from "antd/lib/input";
import AntInputNumber from "antd/lib/input-number";
import AntSelect from "antd/lib/select";
import PlusOutlinedIcon from "@ant-design/icons/PlusOutlined";
import DeleteOutlinedIcon from "@ant-design/icons/DeleteOutlined";
import { UpdateOptionsStrategy } from "@/components/visualizations/editor/createTabbedEditor";
import { Section, Select, InputNumber, ControlLabel } from "@/components/visualizations/editor";
import { ColorSelect } from "../../shared/valueOptions/editor";
import { ReferenceLine, ReferenceBand, DEFAULT_WINDOW } from "../echarts/references";

const KINDS = [
  { value: "value", label: "At a value" },
  { value: "average", label: "Average of a series" },
  { value: "min", label: "Minimum of a series" },
  { value: "max", label: "Maximum of a series" },
  { value: "x", label: "At a point on the x axis" },
];

function numberOrNull(v: any): number | null {
  if (v === null || v === undefined || v === "") {
    return null;
  }
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

export default function ReferenceSettings({ options, onOptionsChange }: any) {
  const lines: ReferenceLine[] = Array.isArray(options.referenceLines) ? options.referenceLines : [];
  const bands: ReferenceBand[] = Array.isArray(options.referenceBands) ? options.referenceBands : [];
  const window = { ...DEFAULT_WINDOW, ...(options.window || {}) };
  const seriesNames = keys(options.seriesOptions || {});

  // Lists are replaced, not merged: a deep merge keeps removed entries.
  const setLines = (next: ReferenceLine[]) =>
    onOptionsChange({ referenceLines: next }, UpdateOptionsStrategy.shallowMerge);
  const setBands = (next: ReferenceBand[]) =>
    onOptionsChange({ referenceBands: next }, UpdateOptionsStrategy.shallowMerge);
  const updateLine = (i: number, changes: Partial<ReferenceLine>) =>
    setLines(lines.map((l, j) => (j === i ? { ...l, ...changes } : l)));
  const updateBand = (i: number, changes: Partial<ReferenceBand>) =>
    setBands(bands.map((b, j) => (j === i ? { ...b, ...changes } : b)));

  return (
    <React.Fragment>
      {/* @ts-expect-error Section's children type is too narrow in its declaration */}
      <Section>
        {/* @ts-expect-error ControlLabel's props are declared too narrowly */}
        <ControlLabel label="Reference lines">
          <p className="value-options-help">A goal, a limit, or a series' average, drawn across the chart.</p>
          <div className="value-options-rows">
            {lines.map((line, i) => (
              <div className="chart-editor-reference" key={i} data-test={`Chart.Reference.Line.${i}`}>
                <div className="value-options-row">
                  <AntSelect
                    value={line.kind}
                    onChange={(kind: any) => updateLine(i, { kind })}
                    data-test={`Chart.Reference.Line.${i}.Kind`}
                    aria-label={`Line ${i + 1} kind`}
                    style={{ flex: 1 }}
                  >
                    {KINDS.map((k) => (
                      <AntSelect.Option key={k.value} value={k.value}>
                        {k.label}
                      </AntSelect.Option>
                    ))}
                  </AntSelect>
                  <Button
                    type="link"
                    aria-label={`Remove line ${i + 1}`}
                    data-test={`Chart.Reference.Line.${i}.Remove`}
                    onClick={() => setLines(lines.filter((_, j) => j !== i))}
                  >
                    <DeleteOutlinedIcon />
                  </Button>
                </div>
                <div className="value-options-row">
                  {line.kind === "value" && (
                    <AntInputNumber
                      placeholder="Value"
                      value={line.value as any}
                      aria-label={`Line ${i + 1} value`}
                      data-test={`Chart.Reference.Line.${i}.Value`}
                      onChange={(v: any) => updateLine(i, { value: numberOrNull(v) })}
                    />
                  )}
                  {line.kind === "x" && (
                    <AntInput
                      placeholder="Category or date"
                      value={(line.value as any) ?? ""}
                      aria-label={`Line ${i + 1} position`}
                      data-test={`Chart.Reference.Line.${i}.Value`}
                      onChange={(e: any) => updateLine(i, { value: e.target.value })}
                    />
                  )}
                  {(line.kind === "average" || line.kind === "min" || line.kind === "max") && (
                    <AntSelect
                      value={line.series || ""}
                      onChange={(series: any) => updateLine(i, { series })}
                      aria-label={`Line ${i + 1} series`}
                      style={{ flex: 1 }}
                    >
                      <AntSelect.Option value="">First series</AntSelect.Option>
                      {seriesNames.map((name) => (
                        <AntSelect.Option key={name} value={name}>
                          {name}
                        </AntSelect.Option>
                      ))}
                    </AntSelect>
                  )}
                  <AntInput
                    placeholder="Label"
                    value={line.label}
                    aria-label={`Line ${i + 1} label`}
                    data-test={`Chart.Reference.Line.${i}.Label`}
                    onChange={(e: any) => updateLine(i, { label: e.target.value })}
                  />
                </div>
                <div className="value-options-row">
                  <ColorSelect value={line.color} onChange={(color) => updateLine(i, { color })} aria-label="Colour" />
                  <AntSelect
                    value={line.style}
                    onChange={(style: any) => updateLine(i, { style })}
                    aria-label={`Line ${i + 1} style`}
                  >
                    <AntSelect.Option value="dashed">Dashed</AntSelect.Option>
                    <AntSelect.Option value="solid">Solid</AntSelect.Option>
                  </AntSelect>
                </div>
              </div>
            ))}
          </div>
          <Button
            className="value-options-add"
            data-test="Chart.Reference.Line.Add"
            onClick={() =>
              setLines([
                ...lines,
                { kind: "value", value: null, series: "", label: "", color: "critical", style: "dashed" },
              ])
            }
          >
            <PlusOutlinedIcon /> Add line
          </Button>
        </ControlLabel>
      </Section>

      {/* @ts-expect-error Section's children type is too narrow in its declaration */}
      <Section>
        {/* @ts-expect-error ControlLabel's props are declared too narrowly */}
        <ControlLabel label="Bands">
          <p className="value-options-help">A shaded range on the value axis. Leave an end empty to run to the edge.</p>
          <div className="value-options-rows">
            {bands.map((band, i) => (
              <div className="value-options-row" key={i} data-test={`Chart.Reference.Band.${i}`}>
                <AntInputNumber
                  placeholder="From"
                  value={band.from as any}
                  aria-label={`Band ${i + 1} from`}
                  data-test={`Chart.Reference.Band.${i}.From`}
                  onChange={(v: any) => updateBand(i, { from: numberOrNull(v) })}
                />
                <AntInputNumber
                  placeholder="To"
                  value={band.to as any}
                  aria-label={`Band ${i + 1} to`}
                  data-test={`Chart.Reference.Band.${i}.To`}
                  onChange={(v: any) => updateBand(i, { to: numberOrNull(v) })}
                />
                <AntInput
                  placeholder="Label"
                  value={band.label}
                  aria-label={`Band ${i + 1} label`}
                  onChange={(e: any) => updateBand(i, { label: e.target.value })}
                />
                <ColorSelect value={band.color} onChange={(color) => updateBand(i, { color })} aria-label="Colour" />
                <Button
                  type="link"
                  aria-label={`Remove band ${i + 1}`}
                  data-test={`Chart.Reference.Band.${i}.Remove`}
                  onClick={() => setBands(bands.filter((_, j) => j !== i))}
                >
                  <DeleteOutlinedIcon />
                </Button>
              </div>
            ))}
          </div>
          <Button
            className="value-options-add"
            data-test="Chart.Reference.Band.Add"
            onClick={() => setBands([...bands, { from: null, to: null, label: "", color: "warning" }])}
          >
            <PlusOutlinedIcon /> Add band
          </Button>
        </ControlLabel>
      </Section>

      {/* @ts-expect-error Section's children type is too narrow in its declaration */}
      <Section>
        <Select
          label="Show"
          value={window.mode}
          data-test="Chart.Window.Mode"
          onChange={(mode: any) => onOptionsChange({ window: { ...window, mode } }, UpdateOptionsStrategy.shallowMerge)}
        >
          {/* @ts-expect-error Select.Option is added by withControlLabel's wrapped component */}
          <Select.Option value="all" data-test="Chart.Window.Mode.all">
            Every point
            {/* @ts-expect-error see above */}
          </Select.Option>
          {/* @ts-expect-error see above */}
          <Select.Option value="points" data-test="Chart.Window.Mode.points">
            The last few points
            {/* @ts-expect-error see above */}
          </Select.Option>
          {/* @ts-expect-error see above */}
          <Select.Option value="minutes" data-test="Chart.Window.Mode.minutes">
            The last few minutes (time axis)
            {/* @ts-expect-error see above */}
          </Select.Option>
        </Select>
        {window.mode !== "all" && (
          <p className="value-options-help">
            For charts that refresh: the line slides along instead of squeezing more in.
          </p>
        )}
      </Section>

      {window.mode === "points" && (
        // @ts-expect-error Section's children type is too narrow in its declaration
        <Section>
          <InputNumber
            label="Points"
            min={1}
            value={window.points}
            data-test="Chart.Window.Points"
            onChange={(points: any) =>
              onOptionsChange(
                { window: { ...window, points: Math.max(1, Math.round(Number(points) || 1)) } },
                UpdateOptionsStrategy.shallowMerge
              )
            }
          />
        </Section>
      )}

      {window.mode === "minutes" && (
        // @ts-expect-error Section's children type is too narrow in its declaration
        <Section>
          <InputNumber
            label="Minutes"
            min={1}
            value={window.minutes}
            data-test="Chart.Window.Minutes"
            onChange={(minutes: any) =>
              onOptionsChange(
                { window: { ...window, minutes: Math.max(1, Number(minutes) || 1) } },
                UpdateOptionsStrategy.shallowMerge
              )
            }
          />
        </Section>
      )}

      {/* @ts-expect-error Section's children type is too narrow in its declaration */}
      <Section>
        <Select
          label="Zoom"
          value={options.zoom || "none"}
          data-test="Chart.Zoom"
          onChange={(zoom: any) => onOptionsChange({ zoom })}
        >
          {/* @ts-expect-error Select.Option is added by withControlLabel's wrapped component */}
          <Select.Option value="none">No</Select.Option>
          {/* @ts-expect-error see above */}
          <Select.Option value="slider">With a slider</Select.Option>
          {/* @ts-expect-error see above */}
          <Select.Option value="inside">With the mouse wheel and dragging</Select.Option>
          {/* @ts-expect-error see above */}
          <Select.Option value="both">Both</Select.Option>
        </Select>
      </Section>
    </React.Fragment>
  );
}
