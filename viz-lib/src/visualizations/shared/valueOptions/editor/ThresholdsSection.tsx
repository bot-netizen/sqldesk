import React from "react";
import Button from "antd/lib/button";
import AntInputNumber from "antd/lib/input-number";
import PlusOutlinedIcon from "@ant-design/icons/PlusOutlined";
import DeleteOutlinedIcon from "@ant-design/icons/DeleteOutlined";
import { Section, ControlLabel } from "@/components/visualizations/editor";
import { Thresholds, ThresholdStep, normalizeThresholds } from "../thresholds";
import ColorSelect from "./ColorSelect";

type Props = {
  thresholds?: Partial<Thresholds> | null;
  onChange: (thresholds: Thresholds) => void;
  testPrefix: string;
  /** Explains what the colours apply to, in this visualization's terms. */
  description?: React.ReactNode;
  /** Let the base be "no colour", for cells that should stay plain below the first step. */
  allowNoneBase?: boolean;
};

// The next step's colour, so adding one does not start as a copy of the last.
const ESCALATION = ["warning", "critical", "serious", "critical"];

export default function ThresholdsSection({ thresholds, onChange, testPrefix, description, allowNoneBase }: Props) {
  // Steps stay in the order they were entered while editing; evaluation sorts
  // them. Re-sorting on every keystroke would move the field being typed in.
  // An empty base means "no colour"; offered only where that makes sense.
  const saved = normalizeThresholds(thresholds).base;
  const base = saved === "" && !allowNoneBase ? "good" : saved;
  const steps: ThresholdStep[] = Array.isArray(thresholds && thresholds.steps)
    ? (thresholds!.steps as ThresholdStep[])
    : [];

  const emit = (nextSteps: ThresholdStep[], nextBase = base) => onChange({ base: nextBase, steps: nextSteps });

  const addStep = () => {
    const last = steps.length ? Number(steps[steps.length - 1].value) || 0 : 0;
    emit([
      ...steps,
      { value: steps.length ? last * 1.25 || last + 10 : 80, color: ESCALATION[steps.length % ESCALATION.length] },
    ]);
  };

  return (
    // @ts-expect-error Section's children type is too narrow in its declaration
    <Section>
      {/* @ts-expect-error ControlLabel's props are declared too narrowly */}
      <ControlLabel label="Thresholds">
        {description && <p className="value-options-help">{description}</p>}
        <div className="value-options-rows" data-test={`${testPrefix}.Thresholds`}>
          <div className="value-options-row">
            <span className="value-options-row-label">Base</span>
            <ColorSelect
              allowNone={allowNoneBase}
              value={base}
              onChange={(color) => emit(steps, color)}
              data-test={`${testPrefix}.Thresholds.Base`}
              aria-label="Base colour"
            />
          </div>
          {steps.map((step, i) => (
            <div className="value-options-row" key={i} data-test={`${testPrefix}.Thresholds.Step.${i}`}>
              <span className="value-options-row-label">From</span>
              <AntInputNumber
                value={step.value as any}
                aria-label={`Threshold ${i + 1} value`}
                data-test={`${testPrefix}.Thresholds.Step.${i}.Value`}
                onChange={(v: any) =>
                  emit(
                    steps.map((s, j) => (j === i ? { ...s, value: v === null || v === "" ? s.value : Number(v) } : s))
                  )
                }
              />
              <ColorSelect
                value={step.color}
                onChange={(color) => emit(steps.map((s, j) => (j === i ? { ...s, color } : s)))}
                data-test={`${testPrefix}.Thresholds.Step.${i}.Color`}
                aria-label={`Threshold ${i + 1} colour`}
              />
              <Button
                type="link"
                aria-label={`Remove threshold ${i + 1}`}
                data-test={`${testPrefix}.Thresholds.Step.${i}.Remove`}
                onClick={() => emit(steps.filter((_, j) => j !== i))}
              >
                <DeleteOutlinedIcon />
              </Button>
            </div>
          ))}
        </div>
        <Button className="value-options-add" onClick={addStep} data-test={`${testPrefix}.Thresholds.Add`}>
          <PlusOutlinedIcon /> Add threshold
        </Button>
      </ControlLabel>
    </Section>
  );
}
